import asyncio
import gc
import warnings

import pytest

from aioscraper.config import RateLimitConfig, RequestRetryConfig, SchedulerConfig
from aioscraper.core.request_manager import RequestManager
from aioscraper.core.session import BaseRequestContextManager, BaseSession
from aioscraper.core.stats import RunStats
from aioscraper.exceptions import TransportTimeout
from aioscraper.holders import MiddlewareHolder
from aioscraper.types import GroupPolicy, Request, Response
from tests.mocks import make_response

NO_RETRIES = RequestRetryConfig(enabled=False)


class _FlakyRequestContextManager(BaseRequestContextManager):
    def __init__(self, request: Request, seen: set[str]):
        super().__init__(request)
        self._seen = seen

    async def __aenter__(self) -> Response:
        if self._request.url not in self._seen:
            self._seen.add(self._request.url)
            raise TransportTimeout(self._request.url, self._request.method, "timed out")

        return make_response(url=self._request.url, method=self._request.method, headers={})


class FlakySession(BaseSession):
    "Fails every URL once with a retryable transport error, then serves it."

    def __init__(self):
        self.attempts = 0
        self._seen: set[str] = set()

    def make_request(self, request: Request) -> BaseRequestContextManager:
        self.attempts += 1
        return _FlakyRequestContextManager(request, self._seen)

    async def _close_client(self): ...


class _GatedRequestContextManager(BaseRequestContextManager):
    def __init__(self, request: Request, gate: asyncio.Event, started: list[Request]):
        super().__init__(request)
        self._gate = gate
        self._started = started

    async def __aenter__(self) -> Response:
        self._started.append(self._request)
        await self._gate.wait()
        return make_response(url=self._request.url, method=self._request.method, headers={})


class GatedSession(BaseSession):
    "Holds each request open until the test lets it through, so a group can be pinned at its ceiling."

    def __init__(self):
        self.in_flight: list[Request] = []
        self._gates: list[asyncio.Event] = []
        self._open = False

    def make_request(self, request: Request) -> BaseRequestContextManager:
        gate = asyncio.Event()
        if self._open:
            gate.set()

        self._gates.append(gate)
        return _GatedRequestContextManager(request, gate, self.in_flight)

    def release_all(self):
        self._open = True
        for gate in self._gates:
            gate.set()

    def release_next(self):
        "Let the oldest request still being held finish, and no other."
        for gate in self._gates:
            if not gate.is_set():
                gate.set()
                return

    async def _close_client(self): ...


def _manager(session: GatedSession, *, group_concurrency: int, concurrent_requests: int = 64) -> RequestManager:
    return RequestManager(
        scheduler_config=SchedulerConfig(concurrent_requests=concurrent_requests),
        rate_limit_config=RateLimitConfig(
            per_group=True,
            default_interval=0.001,
            group_concurrency=group_concurrency,
        ),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=lambda: session,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )


async def test_group_never_exceeds_its_ceiling():
    """A capped group must not hold more scheduler slots than its ceiling."""
    session = GatedSession()
    manager = _manager(session, group_concurrency=3)
    manager.start_listening()

    for i in range(10):
        await manager.sender(Request(url=f"https://api.test.com/{i}"))

    await asyncio.sleep(0.2)
    assert len(session.in_flight) == 3

    session.release_all()
    await manager.wait()
    assert len(session.in_flight) == 10

    await manager.close()


async def test_a_capped_group_does_not_starve_another():
    """The bug the ceiling exists for: a saturated group must leave slots for everyone else."""
    session = GatedSession()
    manager = RequestManager(
        scheduler_config=SchedulerConfig(concurrent_requests=4),
        rate_limit_config=RateLimitConfig(per_group=True, default_interval=0.001, group_concurrency=2),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=lambda: session,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    manager.start_listening()

    for i in range(10):
        await manager.sender(Request(url=f"https://slow.test.com/{i}"))

    await asyncio.sleep(0.1)
    await manager.sender(Request(url="https://fast.test.com/1"))
    await asyncio.sleep(0.1)

    hosts = [Request(url=request.url).url.split("/")[2] for request in session.in_flight]
    assert hosts.count("slow.test.com") == 2
    assert "fast.test.com" in hosts

    session.release_all()
    await manager.wait()
    await manager.close()


async def test_a_group_holding_an_unqueued_attempt_counts_as_active():
    """The regression: an attempt in a group's hands must keep the run alive.

    A popped attempt sits in no queue - not the ready queue, not the delayed heap, not the
    group's own - so a completion check reading only the queues and the scheduler declares the
    run finished with the attempt still to send. The window is microseconds wide, so this pins
    the accounting rather than trying to lose the race on purpose.
    """
    session = GatedSession()
    manager = _manager(session, group_concurrency=1)
    manager.start_listening()

    # two, not more: the second leaves the group's queue when the first is popped, so once the
    # first finishes nothing is queued anywhere
    for i in range(2):
        await manager.sender(Request(url=f"https://api.test.com/{i}"))

    await asyncio.sleep(0.1)
    assert len(session.in_flight) == 1

    listener = asyncio.ensure_future(manager.wait())

    session.release_next()
    await asyncio.sleep(0.2)

    assert not listener.done(), "the run completed with a request still to send"
    assert len(session.in_flight) == 2

    rate_limiter = manager._rate_limiter_manager
    assert rate_limiter._groups["api.test.com"]._queue.empty()
    assert rate_limiter.active, "a group whose only attempt has left its queue reported itself idle"

    session.release_all()
    await asyncio.wait_for(listener, timeout=2.0)

    await manager.close()


async def test_shutdown_while_a_group_is_saturated():
    """Closing must not hang on a group whose worker is blocked waiting for a permit."""
    session = GatedSession()
    manager = _manager(session, group_concurrency=1)
    manager.start_listening()

    for i in range(5):
        await manager.sender(Request(url=f"https://api.test.com/{i}"))

    await asyncio.sleep(0.1)
    assert len(session.in_flight) == 1

    # the worker holds an attempt it can neither send nor put back
    await asyncio.wait_for(manager.close(), timeout=2.0)


async def test_per_group_ceilings_from_group_by():
    """Each group is held to the ceiling its own policy named."""
    session = GatedSession()
    manager = RequestManager(
        scheduler_config=SchedulerConfig(concurrent_requests=64),
        rate_limit_config=RateLimitConfig(per_group=True, default_interval=0.001, group_concurrency=1),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=lambda: session,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
        group_by=lambda request: (
            GroupPolicy("wide", 0.001, 3) if "wide" in request.url else GroupPolicy("narrow", 0.001)
        ),
    )
    manager.start_listening()

    for i in range(5):
        await manager.sender(Request(url=f"https://api.test.com/wide/{i}"))
        await manager.sender(Request(url=f"https://api.test.com/narrow/{i}"))

    await asyncio.sleep(0.2)

    wide = [request for request in session.in_flight if "wide" in request.url]
    narrow = [request for request in session.in_flight if "narrow" in request.url]
    assert len(wide) == 3
    assert len(narrow) == 1  # the group_by left it None, so it took the configured 1

    session.release_all()
    await manager.wait()
    await manager.close()


@pytest.mark.parametrize("group_concurrency", [0, 2])
async def test_retries_do_not_leak_permits(group_concurrency: int):
    """A retried attempt gives its permit back and the group keeps making progress."""
    session = FlakySession()
    stats = RunStats()
    manager = RequestManager(
        scheduler_config=SchedulerConfig(concurrent_requests=64),
        rate_limit_config=RateLimitConfig(
            per_group=True,
            default_interval=0.001,
            group_concurrency=group_concurrency,
        ),
        retry_config=RequestRetryConfig(attempts=2, base_delay=0.001, max_delay=0.01),
        shutdown_check_interval=0.01,
        sessionmaker=lambda: session,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
        stats=stats,
    )
    manager.start_listening()

    for i in range(6):
        await manager.sender(Request(url=f"https://api.test.com/{i}"))

    await asyncio.wait_for(manager.wait(), timeout=5.0)

    assert stats.requests_retried == 6
    assert stats.requests_succeeded == 6
    assert session.attempts == 12

    group = manager._rate_limiter_manager._groups.get("api.test.com")
    if group is not None:
        assert group.in_flight == 0
        assert group._permits is None or group._permits._value == group_concurrency

    await manager.close()


async def test_close_gives_back_every_permit():
    """Closing must leave no permit behind, whatever stage of the hand-off each attempt reached.

    With one slot and one pending place the group saturates at three different points: one request
    runs, one job waits in the scheduler and never starts, and one attempt is stuck inside `spawn`.
    Only the first reaches the release in `_send_request`.
    """
    session = GatedSession()
    manager = RequestManager(
        scheduler_config=SchedulerConfig(concurrent_requests=1, pending_requests=1),
        rate_limit_config=RateLimitConfig(per_group=True, default_interval=0.001, group_concurrency=3),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=lambda: session,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    manager.start_listening()

    for i in range(5):
        await manager.sender(Request(url=f"https://api.test.com/{i}"))

    await asyncio.sleep(0.3)
    group = manager._rate_limiter_manager._groups["api.test.com"]
    assert group.in_flight == 3
    assert group._permits is not None
    assert group._permits._value == 0

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        await manager.close()
        gc.collect()

    assert group.in_flight == 0
    assert group._permits._value == 3
    unawaited = [str(warning.message) for warning in caught if "never awaited" in str(warning.message)]
    assert unawaited == []


async def test_close_frees_a_group_stuck_at_its_ceiling():
    """A worker waiting for a permit must be settled by close(), not left holding the attempt."""
    session = GatedSession()
    manager = _manager(session, group_concurrency=1)
    manager.start_listening()

    for i in range(4):
        await manager.sender(Request(url=f"https://api.test.com/{i}"))

    await asyncio.sleep(0.1)
    group = manager._rate_limiter_manager._groups["api.test.com"]
    assert group.in_flight == 2  # one dispatched, one the worker holds while waiting

    await asyncio.wait_for(manager.close(), timeout=2.0)

    assert group.in_flight == 0
    assert group._permits is not None
    assert group._permits._value == 1
