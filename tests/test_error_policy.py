import asyncio
import logging
from pathlib import Path
from textwrap import dedent

import pytest

from aioscraper.cli.__main__ import main
from aioscraper.config import (
    Config,
    ErrorPolicy,
    ExecutionConfig,
    RateLimitConfig,
    RequestRetryConfig,
    SchedulerConfig,
)
from aioscraper.core import AIOScraper
from aioscraper.core.errors import ErrorCollector, RunResult
from aioscraper.core.request_manager import RequestManager
from aioscraper.core.runner import _run_scraper
from aioscraper.holders import MiddlewareHolder
from aioscraper.types import Request, Response
from tests.mocks import MockAIOScraper, MockResponse
from tests.test_request_manager import FakeSession, FixedStatusSession


def _manager(collector: ErrorCollector, session_factory) -> RequestManager:
    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(),
        retry_config=RequestRetryConfig(),
        shutdown_check_interval=0.01,
        sessionmaker=session_factory,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
        error_collector=collector,
    )
    manager.start_listening()
    return manager


async def test_request_without_errback_is_recorded():
    """A request failing without an errback is the case that used to vanish into the log."""
    collector = ErrorCollector()
    manager = _manager(collector, lambda: FixedStatusSession(status=500, body="server error"))

    await manager._send_request(Request(url="https://api.test.com/boom"))

    assert len(collector) == 1
    assert collector.errors[0].context == "request"
    assert collector.errors[0].exception.status_code == 500  # type: ignore[reportAttributeAccessIssue]

    await manager.close()


async def test_handled_request_failure_is_not_recorded():
    """A failure the user handled in an errback is not a failure of the run."""
    collector = ErrorCollector()
    handled: list[Exception] = []

    async def errback(exc: Exception):
        handled.append(exc)

    manager = _manager(collector, lambda: FixedStatusSession(status=500, body="server error"))

    await manager._send_request(Request(url="https://api.test.com/boom", errback=errback))

    assert len(handled) == 1
    assert not collector

    await manager.close()


async def test_failing_errback_is_recorded_once():
    """A failing errback escapes _send_request, so only the scheduler wrapper can record it."""
    collector = ErrorCollector()
    called = asyncio.Event()

    async def errback(exc: Exception):
        called.set()
        raise ValueError("errback boom")

    manager = _manager(collector, lambda: FixedStatusSession(status=500, body="server error"))

    # Through the sender: the recording happens in the scheduler wrapper around
    # _send_request, which a direct call bypasses.
    await manager.sender(Request(url="https://api.test.com/boom", errback=errback))
    await asyncio.wait_for(called.wait(), timeout=5.0)
    await asyncio.wait_for(manager.shutdown(), timeout=5.0)

    assert collector.total == 1
    assert collector.counts == {"request": 1}
    assert isinstance(collector.errors[0].exception, ExceptionGroup)

    await manager.close()


async def test_successful_request_records_nothing():
    collector = ErrorCollector()
    seen: list[str] = []

    async def callback(response: Response):
        seen.append(response.url)

    manager = _manager(collector, FakeSession)

    await manager._send_request(Request(url="https://api.test.com/ok", callback=callback))

    assert seen
    assert not collector

    await manager.close()


async def test_scraper_exposes_unhandled_errors(mock_aioscraper: MockAIOScraper):
    """End to end: a failing request with no errback surfaces on AIOScraper.errors."""
    mock_aioscraper.server.add(
        "https://api.test.com/broken",
        handler=lambda _: MockResponse(status=500, text="boom"),
    )

    @mock_aioscraper
    async def scraper(send_request):
        await send_request(Request(url="https://api.test.com/broken"))

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert len(mock_aioscraper.errors) == 1
    assert mock_aioscraper.errors[0].context == "request"


async def test_scraper_without_errors_is_clean(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/ok", handler=lambda _: {"status": "ok"})

    @mock_aioscraper
    async def scraper(send_request):
        await send_request(Request(url="https://api.test.com/ok"))

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert mock_aioscraper.errors == ()


def _entrypoint(tmp_path: Path, policy: ErrorPolicy | None = None) -> Path:
    config = "Config()" if policy is None else f"Config(execution=ExecutionConfig(on_error=ErrorPolicy.{policy.name}))"
    path = tmp_path / "failing_scraper.py"
    path.write_text(
        dedent(f"""
        from aioscraper import AIOScraper, Request
        from aioscraper.config import Config, ErrorPolicy, ExecutionConfig

        scraper = AIOScraper(config={config})

        @scraper
        async def run(send_request):
            await send_request(Request(url="http://127.0.0.1:1/unreachable"))
        """),
    )
    return path


def test_cli_exits_non_zero_on_unhandled_error(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    """Losing data used to still exit 0."""
    with caplog.at_level(logging.ERROR):
        exit_code = main([str(_entrypoint(tmp_path, ErrorPolicy.FAIL))])

    assert exit_code == 1
    assert any("unhandled error" in record.message.lower() for record in caplog.records)


def test_cli_fails_by_default(tmp_path: Path):
    """An ETL job losing data must not look successful to cron/CI without being told to."""
    assert main([str(_entrypoint(tmp_path))]) == 1


def test_cli_exits_zero_under_log_policy(tmp_path: Path):
    assert main([str(_entrypoint(tmp_path, ErrorPolicy.LOG))]) == 0


def test_allow_partial_success_flag_exits_zero(tmp_path: Path):
    assert main([str(_entrypoint(tmp_path)), "--allow-partial-success"]) == 0


def _slow_entrypoint(tmp_path: Path) -> Path:
    path = tmp_path / "slow_scraper.py"
    path.write_text(
        dedent("""
        import asyncio

        from aioscraper import AIOScraper
        from aioscraper.config import Config, ExecutionConfig

        scraper = AIOScraper(config=Config(execution=ExecutionConfig(timeout=0.05)))

        @scraper
        async def run(send_request):
            await asyncio.sleep(30)
        """),
    )
    return path


def test_cli_exits_124_on_execution_timeout(tmp_path: Path):
    """A run cut short by the budget left work unattempted, so it is not a success."""
    assert main([str(_slow_entrypoint(tmp_path))]) == 124


def test_allow_partial_success_does_not_waive_a_timeout(tmp_path: Path):
    """The flag waives recorded errors, not an unfinished run."""
    assert main([str(_slow_entrypoint(tmp_path)), "--allow-partial-success"]) == 124


def test_cli_exits_zero_without_errors(tmp_path: Path):
    path = tmp_path / "clean_scraper.py"
    path.write_text(
        dedent("""
        from aioscraper import AIOScraper

        scraper = AIOScraper()
        """),
    )

    assert main([str(path)]) == 0


def test_fail_is_the_default_policy():
    assert Config().execution.on_error is ErrorPolicy.FAIL


def test_collector_caps_retained_exceptions_but_not_counts():
    """Tracebacks keep frames alive, so a run failing millions of requests must not grow."""
    collector = ErrorCollector(max_retained=3)

    for i in range(1000):
        collector.record("request", ValueError(f"boom {i}"))

    assert collector.total == 1000
    assert collector.counts == {"request": 1000}
    assert len(collector.errors) == 3
    # Most recent, not first: those are the ones worth keeping when debugging.
    assert [str(error.exception) for error in collector.errors] == ["boom 997", "boom 998", "boom 999"]


def test_collector_counts_are_per_context():
    collector = ErrorCollector()
    collector.record("request", ValueError("a"))
    collector.record("close", ValueError("b"))
    collector.record("request", ValueError("c"))

    assert collector.counts == {"request": 2, "close": 1}
    assert collector.total == 3


async def test_run_scraper_reports_signal_shutdown():
    """The runner turns SIGINT into an event, so it must report the stop itself."""
    scraper = AIOScraper()
    shutdown = asyncio.Event()
    shutdown.set()

    result = await _run_scraper(scraper, shutdown_event=shutdown, install_signal_handlers=False)

    assert result.interrupted is True
    assert result.ok is False


async def test_run_scraper_reports_normal_completion():
    scraper = AIOScraper()

    result = await _run_scraper(scraper, install_signal_handlers=False)

    assert result.interrupted is False
    assert result.error_counts == {}
    assert result.total_errors == 0
    assert result.ok is True


async def test_run_scraper_reports_timeout():
    scraper = AIOScraper(config=Config(execution=ExecutionConfig(timeout=0.05)))

    @scraper
    async def run(send_request):
        await asyncio.sleep(30)

    result = await _run_scraper(scraper, install_signal_handlers=False)

    assert result.timed_out is True
    assert result.error_counts == {}
    assert result.ok is False


async def test_run_scraper_returns_recorded_errors():
    """The outcome must be readable from the return value, not only from the scraper."""
    scraper = AIOScraper()

    @scraper
    async def run(send_request):
        await send_request(Request(url="http://127.0.0.1:1/unreachable"))

    result = await _run_scraper(scraper, install_signal_handlers=False)

    assert result.error_counts == {"request": 1}
    assert result.total_errors == 1
    assert result.ok is False
    assert [error.context for error in result.errors] == ["request"]


async def test_wait_returns_the_outcome():
    scraper = AIOScraper()

    @scraper
    async def run(send_request):
        await send_request(Request(url="http://127.0.0.1:1/unreachable"))

    async with scraper:
        result = await scraper.wait()

    assert result.error_counts == {"request": 1}
    assert result.timed_out is False
    assert result.ok is False


def test_cli_exits_130_when_stopped_by_signal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """KeyboardInterrupt never reaches the CLI, so 130 has to come from the runner flag."""

    async def fake_run_scraper(scraper) -> RunResult:
        return RunResult(interrupted=True)

    monkeypatch.setattr("aioscraper.cli.__main__.run_scraper", fake_run_scraper)

    assert main([str(_entrypoint(tmp_path, ErrorPolicy.FAIL))]) == 130
