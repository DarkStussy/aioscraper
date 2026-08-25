import asyncio
from typing import Callable

import pytest

from aioscraper.config import BackoffStrategy, RateLimitConfig, RequestRetryConfig, SchedulerConfig
from aioscraper.core.request_manager import RequestManager
from aioscraper.core.session import BaseSession
from aioscraper.holders import MiddlewareHolder
from aioscraper.types import Request, ScheduleRequest
from tests.test_request_manager import FakeSession, FixedStatusSession


def _manager(
    *,
    max_pending: int,
    session_factory: Callable[[], BaseSession] = FakeSession,
    middleware_holder: MiddlewareHolder | None = None,
    retry_config: RequestRetryConfig | None = None,
    rate_limit_config: RateLimitConfig | None = None,
    concurrent_requests: int = 64,
    pending_requests: int = 1,
) -> RequestManager:
    return RequestManager(
        scheduler_config=SchedulerConfig(
            ready_queue_max_size=max_pending,
            concurrent_requests=concurrent_requests,
            pending_requests=pending_requests,
        ),
        rate_limit_config=rate_limit_config or RateLimitConfig(),
        retry_config=retry_config or RequestRetryConfig(),
        shutdown_check_interval=0.01,
        sessionmaker=session_factory,
        dependencies={},
        middleware_holder=middleware_holder or MiddlewareHolder(),
    )


async def test_sender_blocks_when_pending_is_full():
    """Without a consumer the second request must not be accepted."""
    manager = _manager(max_pending=1)

    await manager.sender(Request(url="https://api.test.com/1"))

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(manager.sender(Request(url="https://api.test.com/2")), timeout=0.1)

    await manager.close()


async def test_delayed_requests_count_towards_the_limit():
    """The bug: delayed retries went into an unbounded heap and bypassed the limit."""
    manager = _manager(max_pending=1)

    await manager.sender(Request(url="https://api.test.com/1", delay=30.0))

    assert len(manager._delayed_heap) == 1
    assert manager._ready_queue.empty()

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(manager.sender(Request(url="https://api.test.com/2")), timeout=0.1)

    await manager.close()


async def test_consuming_a_request_frees_a_slot():
    manager = _manager(max_pending=1)

    await manager.sender(Request(url="https://api.test.com/1"))

    async def send_second() -> Request:
        return await manager.sender(Request(url="https://api.test.com/2"))

    blocked = asyncio.create_task(send_second())
    await asyncio.sleep(0.05)
    assert not blocked.done()

    manager.start_listening()

    await asyncio.wait_for(blocked, timeout=5.0)
    await asyncio.wait_for(manager.shutdown(), timeout=5.0)
    await manager.close()


async def test_unlimited_by_default():
    manager = _manager(max_pending=0)

    for i in range(50):
        await asyncio.wait_for(manager.sender(Request(url=f"https://api.test.com/{i}")), timeout=1.0)

    assert manager._ready_queue.qsize() == 50

    await manager.close()


async def test_retry_storm_does_not_deadlock():
    """Retries are enqueued from inside a request job, so a full pending set blocks a
    worker. The listener must still drain and let everything finish."""
    retry_config = RequestRetryConfig(
        enabled=True,
        attempts=2,
        backoff=BackoffStrategy.CONSTANT,
        base_delay=0.01,
    )
    manager = _manager(
        max_pending=2,
        session_factory=lambda: FixedStatusSession(status=503, body="unavailable"),
        retry_config=retry_config,
    )
    manager.start_listening()

    for i in range(10):
        await asyncio.wait_for(manager.sender(Request(url=f"https://api.test.com/{i}")), timeout=10.0)

    await asyncio.wait_for(manager.shutdown(), timeout=30.0)

    assert manager._ready_queue.empty()
    assert not manager._delayed_heap

    await manager.close()


async def test_rate_limited_group_does_not_bypass_the_limit():
    """The rate limiter group queue is unbounded, so the slot must be held until the
    request reaches the scheduler, not released when it leaves the ready queue."""
    # A long interval keeps the group holding requests instead of draining them.
    manager = _manager(max_pending=1, rate_limit_config=RateLimitConfig(enabled=True, default_interval=5.0))
    manager.start_listening()

    accepted = 0
    try:
        for i in range(20):
            await asyncio.wait_for(manager.sender(Request(url=f"https://api.test.com/{i}")), timeout=0.2)
            accepted += 1
    except TimeoutError:
        pass

    # One in the scheduler plus one parked in the group; the rest must not be accepted.
    assert accepted <= 3, f"{accepted} requests were accepted despite max_pending=1"

    await manager.close()


async def test_retry_does_not_deadlock_with_a_single_worker():
    """The tightest configuration: one worker, one pending job, one pending slot."""
    retry_config = RequestRetryConfig(
        enabled=True,
        attempts=2,
        backoff=BackoffStrategy.CONSTANT,
        base_delay=0.01,
    )
    manager = _manager(
        max_pending=1,
        concurrent_requests=1,
        pending_requests=1,
        session_factory=lambda: FixedStatusSession(status=503, body="unavailable"),
        retry_config=retry_config,
    )
    manager.start_listening()

    for i in range(4):
        await asyncio.wait_for(manager.sender(Request(url=f"https://api.test.com/{i}")), timeout=10.0)

    await asyncio.wait_for(manager.shutdown(), timeout=15.0)
    await manager.close()


async def test_send_from_inside_a_job_does_not_wait_for_a_slot():
    """A job occupies a scheduler slot, and slots are freed by the listener, which needs
    the scheduler to accept the next request. Blocking here deadlocks both."""
    manager = _manager(max_pending=1, concurrent_requests=1, pending_requests=1)
    sent = 0
    finished = asyncio.Event()

    async def callback(schedule_request: ScheduleRequest):
        nonlocal sent
        # More follow-ups than the scheduler can take, so the listener stops releasing
        # slots partway through and a waiting sender would never resume.
        for i in range(5):
            await schedule_request(Request(url=f"https://api.test.com/followup-{i}"))
            sent += 1

        finished.set()

    manager.start_listening()
    await manager.sender(Request(url="https://api.test.com/1", callback=callback))

    await asyncio.wait_for(finished.wait(), timeout=2.0)
    assert sent == 5

    await manager.close()


async def test_resending_the_same_request_object_frees_both_slots():
    """The reservation lives on the queue entry: one Request object can be queued twice."""
    manager = _manager(max_pending=2)
    request = Request(url="https://api.test.com/1")

    await manager.sender(request)
    await manager.sender(request)
    assert manager._pending_slots.count == 2

    manager.start_listening()
    await asyncio.wait_for(manager.shutdown(), timeout=5.0)

    assert manager._pending_slots.count == 0

    await manager.close()


async def test_job_sends_are_counted_although_they_do_not_wait():
    """Skipping the wait must not skip the accounting, or the entrypoint stops throttling."""
    manager = _manager(max_pending=1)

    await manager._job_sender(Request(url="https://api.test.com/1", delay=30.0))
    assert manager._pending_slots.count == 1

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(manager.sender(Request(url="https://api.test.com/2")), timeout=0.1)

    await manager.close()
