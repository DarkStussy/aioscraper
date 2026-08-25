import asyncio

import pytest

from aioscraper.config import (
    BackoffStrategy,
    Config,
    RateLimitConfig,
    RequestRetryConfig,
    SchedulerConfig,
    SessionConfig,
)
from aioscraper.core.request_manager import RequestManager
from aioscraper.core.session import BaseSession
from aioscraper.holders import MiddlewareHolder
from aioscraper.types import Request, Response, ScheduleRequest
from aioscraper.types.session import Attempt
from tests.mocks import MockAIOScraper, MockResponse
from tests.test_request_manager import FixedStatusSession

# Long enough that a re-admitted request stays parked in the delayed heap for the assertions.
PARKED_DELAY = 30.0
NO_RETRIES = RequestRetryConfig(enabled=False)


def _manager(
    *,
    retry_config: RequestRetryConfig,
    session_factory: type[BaseSession] | None = None,
) -> RequestManager:
    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(),
        retry_config=retry_config,
        shutdown_check_interval=0.01,
        sessionmaker=session_factory or (lambda: FixedStatusSession(status=503, body="unavailable")),
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    manager.start_listening()
    return manager


def _retries_reached(manager: RequestManager, count: int) -> asyncio.Event:
    "Fires once ``count`` failures have gone through the retry decision."
    reached = asyncio.Event()
    retry = manager._retry
    seen = 0

    async def spy(attempt: Attempt, exc: Exception) -> bool:
        nonlocal seen
        result = await retry(attempt, exc)
        seen += 1
        if seen >= count:
            reached.set()

        return result

    manager._retry = spy  # type: ignore[reportAttributeAccessIssue]
    return reached


async def test_concurrent_sends_of_one_object_get_their_own_retry_budget():
    """The bug: both chains shared one counter on the request, so together they got one budget."""
    manager = _manager(
        retry_config=RequestRetryConfig(
            enabled=True,
            attempts=1,
            backoff=BackoffStrategy.CONSTANT,
            base_delay=PARKED_DELAY,
            statuses=(503,),
        ),
    )
    decided = _retries_reached(manager, 2)
    request = Request(url="https://api.test.com/flaky")

    try:
        await manager.sender(request)
        await manager.sender(request)
        await asyncio.wait_for(decided.wait(), timeout=5.0)

        # One parked retry per send, each on its first retry.
        assert [parked.retries for parked in manager._delayed_heap] == [1, 1]
        assert request.state == {}
        assert request.delay is None
    finally:
        manager._delayed_heap.clear()
        await asyncio.wait_for(manager.shutdown(), timeout=5.0)
        await manager.close()


async def test_a_later_send_does_not_inherit_the_previous_budget():
    """Re-running the same object used to start with the retry counter of the finished run."""
    retry_config = RequestRetryConfig(
        enabled=True,
        attempts=1,
        backoff=BackoffStrategy.CONSTANT,
        base_delay=PARKED_DELAY,
        statuses=(503,),
    )
    request = Request(url="https://api.test.com/flaky")

    for _ in range(2):
        manager = _manager(retry_config=retry_config)
        decided = _retries_reached(manager, 1)

        try:
            await manager.sender(request)
            await asyncio.wait_for(decided.wait(), timeout=5.0)

            assert [parked.retries for parked in manager._delayed_heap] == [1]
        finally:
            manager._delayed_heap.clear()
            await asyncio.wait_for(manager.shutdown(), timeout=5.0)
            await manager.close()


async def test_user_delay_applies_to_every_send():
    """The delayed heap used to clear Request.delay, so a later send skipped the delay."""
    manager = _manager(retry_config=NO_RETRIES)
    request = Request(url="https://api.test.com/slow", delay=0.001)

    try:
        await manager.sender(request)
        assert len(manager._delayed_heap) == 1

        # comfortably past the ~15.6ms granularity of monotonic() on Windows, where a 10ms sleep
        # can leave the clock, and with it the entry's due time, where it was
        await asyncio.sleep(0.1)
        await manager._pop_due_delayed()
        assert not manager._delayed_heap
        assert request.delay == 0.001

        await manager.sender(request)
        assert len(manager._delayed_heap) == 1
    finally:
        manager._delayed_heap.clear()
        await manager.close()


class RetryScraper:
    def __init__(self, url: str, sends: int = 1):
        self.url = url
        self.sends = sends
        self.callbacks = 0
        self.errbacks = 0
        self.request = Request(url=url, callback=self.handle_response, errback=self.handle_error)

    async def __call__(self, schedule_request: ScheduleRequest):
        for _ in range(self.sends):
            await schedule_request(self.request)

    async def handle_response(self, response: Response):
        self.callbacks += 1

    async def handle_error(self, exc: Exception):
        self.errbacks += 1


def _retry_config(**overrides) -> Config:
    settings = {
        "enabled": True,
        "attempts": 2,
        "base_delay": 0.05,
        "statuses": (502,),
        "backoff": BackoffStrategy.CONSTANT,
        **overrides,
    }
    return Config(session=SessionConfig(retry=RequestRetryConfig(**settings)))


@pytest.mark.asyncio
async def test_retry_succeeds_after_transient_failures(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add(
        "https://api.test.com/flaky",
        handler=lambda _: MockResponse(status=502),
        repeat=2,
    )
    mock_aioscraper.server.add("https://api.test.com/flaky", handler=lambda _: {"ok": True})

    scraper = RetryScraper("https://api.test.com/flaky")
    mock_aioscraper(scraper)
    mock_aioscraper.config = _retry_config()

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert scraper.callbacks == 1
    assert scraper.errbacks == 0
    mock_aioscraper.server.assert_all_routes_handled()


@pytest.mark.asyncio
async def test_errback_runs_once_attempts_are_exhausted(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add(
        "https://api.test.com/always-bad",
        handler=lambda _: MockResponse(status=502),
        repeat=3,
    )

    scraper = RetryScraper("https://api.test.com/always-bad")
    mock_aioscraper(scraper)
    mock_aioscraper.config = _retry_config()

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert scraper.callbacks == 0
    assert scraper.errbacks == 1
    mock_aioscraper.server.assert_all_routes_handled()


@pytest.mark.asyncio
async def test_each_send_of_one_object_is_retried_end_to_end(mock_aioscraper: MockAIOScraper):
    """Two sends of one object must produce two independent budgets: 2 x (1 + 1 retry)."""
    mock_aioscraper.server.add(
        "https://api.test.com/always-bad",
        handler=lambda _: MockResponse(status=502),
        repeat=4,
    )

    scraper = RetryScraper("https://api.test.com/always-bad", sends=2)
    mock_aioscraper(scraper)
    mock_aioscraper.config = _retry_config(attempts=1)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert scraper.callbacks == 0
    assert scraper.errbacks == 2
    mock_aioscraper.server.assert_all_routes_handled()


@pytest.mark.asyncio
async def test_should_retry_hook_runs_end_to_end(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add(
        "https://api.test.com/teapot",
        handler=lambda _: MockResponse(status=418),
        repeat=2,
    )
    mock_aioscraper.server.add("https://api.test.com/teapot", handler=lambda _: {"ok": True})

    scraper = RetryScraper("https://api.test.com/teapot")
    mock_aioscraper(scraper)
    # 418 is in neither statuses nor exceptions: only the hook can keep the request alive.
    mock_aioscraper.config = _retry_config(statuses=())
    mock_aioscraper.should_retry = lambda request, exc, retries: getattr(exc, "status_code", None) == 418

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert scraper.callbacks == 1
    assert scraper.errbacks == 0
    mock_aioscraper.server.assert_all_routes_handled()
