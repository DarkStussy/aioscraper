import asyncio
import os
import signal
import sys
from contextlib import suppress
from types import FrameType
from unittest.mock import AsyncMock

import pytest

from aioscraper.config import Config, ExecutionConfig
from aioscraper.core import AIOScraper
from aioscraper.core.errors import RunResult
from aioscraper.core.runner import _run_scraper, _run_scraper_without_force_exit, run_scraper


def make_scraper_mock() -> AsyncMock:
    scraper = AsyncMock()
    scraper.entered = False
    scraper.exited = False
    scraper.started = False
    scraper.canceled = False
    scraper.canceled_by_timeout = False
    scraper._stop = asyncio.Event()
    scraper.result = RunResult()

    async def aenter():
        scraper.entered = True
        return scraper

    async def aexit(exc_type, exc_val, exc_tb):
        scraper.exited = True

    async def wait():
        scraper.started = True
        try:
            await asyncio.wait_for(scraper._stop.wait(), scraper.config.execution.timeout)
        except TimeoutError:
            scraper.canceled = True
            scraper.canceled_by_timeout = True
        except asyncio.CancelledError:
            scraper.canceled = True
            raise

    scraper.__aenter__.side_effect = aenter
    scraper.__aexit__.side_effect = aexit
    scraper.wait.side_effect = wait
    scraper.stop = scraper._stop.set
    return scraper


@pytest.mark.asyncio
async def test_shutdown_event_cancels_scraper():
    scraper = make_scraper_mock()
    scraper.config = Config(execution=ExecutionConfig(timeout=None, shutdown_timeout=0.05))
    shutdown = asyncio.Event()

    async def trigger_shutdown():
        await asyncio.sleep(0.01)
        shutdown.set()

    trigger = asyncio.create_task(trigger_shutdown())
    await _run_scraper_without_force_exit(scraper, shutdown)
    trigger.cancel()
    with suppress(asyncio.CancelledError):
        await trigger

    assert scraper.entered is True
    assert scraper.exited is True
    assert scraper.started is True
    assert scraper.canceled is True


@pytest.mark.asyncio
async def test_shutdown_grants_grace_period_to_in_flight_work():
    """In-flight work that finishes inside shutdown_timeout must not be canceled."""
    scraper = make_scraper_mock()
    scraper.config = Config(execution=ExecutionConfig(timeout=None, shutdown_timeout=0.5))
    shutdown = asyncio.Event()

    async def trigger_shutdown():
        await asyncio.sleep(0.01)
        shutdown.set()
        # 150ms of work after the signal, well inside the 500ms grace period.
        await asyncio.sleep(0.15)
        scraper.stop()

    trigger = asyncio.create_task(trigger_shutdown())
    await _run_scraper_without_force_exit(scraper, shutdown)
    await trigger

    assert scraper.started is True
    assert scraper.exited is True
    assert scraper.canceled is False


@pytest.mark.asyncio
async def test_execution_timeout_cancels_scraper():
    scraper = make_scraper_mock()
    scraper.config = Config(execution=ExecutionConfig(timeout=0.02, shutdown_timeout=0.01))
    shutdown = asyncio.Event()

    await _run_scraper_without_force_exit(scraper, shutdown)

    assert scraper.canceled is True
    assert scraper.canceled_by_timeout is True


@pytest.mark.asyncio
async def test_force_exit_path():
    scraper = make_scraper_mock()
    scraper.config = Config(execution=ExecutionConfig(timeout=None, shutdown_timeout=0.05))
    shutdown = asyncio.Event()
    force_exit = asyncio.Event()

    async def trigger_force_exit():
        shutdown.set()
        await asyncio.sleep(0.01)
        force_exit.set()

    trigger = asyncio.create_task(trigger_force_exit())
    await _run_scraper(
        scraper,
        shutdown_event=shutdown,
        force_exit_event=force_exit,
        install_signal_handlers=False,
    )
    trigger.cancel()
    with suppress(asyncio.CancelledError):
        await trigger

    assert scraper.canceled is True


def _app_handler(signum: int, frame: FrameType | None):
    pass


@pytest.fixture
def app_sigterm_handler():
    "Stands in for an application's SIGTERM handler."
    original = signal.getsignal(signal.SIGTERM)
    signal.signal(signal.SIGTERM, _app_handler)
    try:
        yield _app_handler
    finally:
        signal.signal(signal.SIGTERM, original)


@pytest.mark.asyncio
async def test_run_scraper_puts_the_previous_handler_back(app_sigterm_handler):
    await run_scraper(AIOScraper(config=Config()))

    assert signal.getsignal(signal.SIGTERM) is app_sigterm_handler


@pytest.mark.asyncio
async def test_run_scraper_can_leave_signals_alone(app_sigterm_handler):
    seen: list[object] = []
    scraper = AIOScraper(config=Config())

    @scraper
    async def run():
        seen.append(signal.getsignal(signal.SIGTERM))

    await run_scraper(scraper, install_signal_handlers=False)

    assert seen == [app_sigterm_handler]


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="os.kill cannot deliver SIGTERM to a handler on Windows")
async def test_run_scraper_turns_sigterm_into_a_graceful_shutdown(app_sigterm_handler):
    scraper = AIOScraper(config=Config(execution=ExecutionConfig(shutdown_timeout=0.05)))

    @scraper
    async def run():
        os.kill(os.getpid(), signal.SIGTERM)
        await asyncio.sleep(30)

    result = await asyncio.wait_for(run_scraper(scraper), timeout=5.0)

    assert result.interrupted is True
    assert signal.getsignal(signal.SIGTERM) is app_sigterm_handler


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="os.kill cannot deliver SIGTERM to a handler on Windows")
async def test_a_run_ending_early_keeps_the_handlers_of_one_still_going(app_sigterm_handler):
    first = AIOScraper(config=Config())
    second = AIOScraper(config=Config(execution=ExecutionConfig(shutdown_timeout=0.05)))
    second_started = asyncio.Event()

    @first
    async def run_first():
        await second_started.wait()

    @second
    async def run_second():
        second_started.set()
        await asyncio.sleep(30)

    second_run = asyncio.create_task(run_scraper(second))
    await run_scraper(first)

    os.kill(os.getpid(), signal.SIGTERM)
    result = await asyncio.wait_for(second_run, timeout=5.0)

    assert result.interrupted is True
    assert signal.getsignal(signal.SIGTERM) is app_sigterm_handler


@pytest.mark.asyncio
@pytest.mark.skipif(sys.platform == "win32", reason="os.kill cannot deliver SIGTERM to a handler on Windows")
async def test_a_signal_reaches_every_overlapping_run(app_sigterm_handler):
    scrapers = [AIOScraper(config=Config(execution=ExecutionConfig(shutdown_timeout=0.05))) for _ in range(2)]
    started = [asyncio.Event() for _ in scrapers]

    for scraper, event in zip(scrapers, started, strict=True):

        @scraper
        async def run(event: asyncio.Event = event):
            event.set()
            await asyncio.sleep(30)

    runs = [asyncio.create_task(run_scraper(scraper)) for scraper in scrapers]
    for event in started:
        await event.wait()

    os.kill(os.getpid(), signal.SIGTERM)
    results = await asyncio.wait_for(asyncio.gather(*runs), timeout=5.0)

    assert [result.interrupted for result in results] == [True, True]
    assert signal.getsignal(signal.SIGTERM) is app_sigterm_handler
