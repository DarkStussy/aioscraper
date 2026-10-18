import asyncio
import math
from dataclasses import replace
from typing import Any

import pytest
from yarl import URL

from aioscraper.config import (
    AdaptiveRateLimitConfig,
    BackoffStrategy,
    RateLimitConfig,
    RequestRetryConfig,
    SchedulerConfig,
)
from aioscraper.core.rate_limiter import RequestOutcome
from aioscraper.core.request_manager import RequestManager
from aioscraper.core.retry import RetryPolicy
from aioscraper.core.session import BaseRequestContextManager, BaseSession
from aioscraper.core.session.httpx import HttpxSession
from aioscraper.exceptions import (
    AIOScraperException,
    HTTPException,
    InvalidRequestData,
    TransportTimeout,
    UnsupportedRequestOption,
)
from aioscraper.holders import MiddlewareHolder
from aioscraper.types import File, GroupPolicy, Request, RequestHandler, RequestMiddleware, Response
from aioscraper.types.session import Attempt
from tests.mocks import make_response

NO_RETRIES = RequestRetryConfig(enabled=False)


def _http_error(status: int = 503) -> HTTPException:
    return HTTPException(url="https://api.test.com/flaky", method="GET", status_code=status, headers={}, message="")


def attempt(request: Request, *, retries: int = 0) -> Attempt:
    "Wrap a request the way the queue would before it reaches _send_request."
    return Attempt(
        priority=request.priority,
        request=request,
        retries=retries,
        group_key=URL(request.url).host,
    )


class FakeRequestContextManager(BaseRequestContextManager):
    async def __aenter__(self) -> Response:
        return make_response(url=self._request.url, method=self._request.method, headers={})


class FakeSession(BaseSession):
    def __init__(self):
        self.closed = False
        self.calls = 0

    def make_request(self, request: Request) -> FakeRequestContextManager:
        return FakeRequestContextManager(request)

    async def _close_client(self):
        self.closed = True


def _build_response(request: Request, *, status: int, body: str = "") -> Response:
    return make_response(body.encode(), url=request.url, method=request.method, status=status)


class FixedStatusRequestContextManager(BaseRequestContextManager):
    def __init__(self, request: Request, *, status: int, body: str):
        super().__init__(request)
        self._status = status
        self._body = body

    async def __aenter__(self) -> Response:
        return _build_response(self._request, status=self._status, body=self._body)


class FixedStatusSession(BaseSession):
    def __init__(self, *, status: int, body: str = "boom"):
        self._status = status
        self._body = body

    def make_request(self, request: Request) -> BaseRequestContextManager:
        return FixedStatusRequestContextManager(request, status=self._status, body=self._body)

    async def _close_client(self): ...


class NoopSession(BaseSession):
    def make_request(self, request: Request) -> BaseRequestContextManager:
        raise AssertionError("should not be called when validation fails")

    async def _close_client(self): ...


@pytest.fixture
def middleware_holder() -> MiddlewareHolder:
    return MiddlewareHolder()


@pytest.fixture
def base_manager_factory(middleware_holder: MiddlewareHolder):
    def factory(*, session_factory, default_interval=0.0):
        manager = RequestManager(
            scheduler_config=SchedulerConfig(),
            rate_limit_config=RateLimitConfig(default_interval=default_interval),
            retry_config=NO_RETRIES,
            shutdown_check_interval=0.01,
            sessionmaker=session_factory,
            dependencies={},
            middleware_holder=middleware_holder,
        )
        manager.start_listening()
        return manager

    return factory


@pytest.mark.asyncio
async def test_errback_failure_wrapped_in_exception_group():
    """Test that errback exceptions are wrapped in ExceptionGroup with original exception."""

    async def errback(exc: Exception):
        raise ValueError("errback failed")

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    manager.start_listening()

    with pytest.raises(ExceptionGroup) as excinfo:
        await manager._handle_exception(
            Request(url="https://api.test.com/errback", errback=errback),
            RuntimeError("boom"),
        )

    assert len(excinfo.value.exceptions) == 2
    assert isinstance(excinfo.value.exceptions[0], RuntimeError)
    assert isinstance(excinfo.value.exceptions[1], ValueError)

    await manager.close()


@pytest.mark.asyncio
async def test_request_manager_respects_delay_between_requests(base_manager_factory):
    """Test that request manager respects the configured delay between requests."""
    call_times: list[float] = []
    seen: list[str] = []
    default_interval = 0.1
    finished = asyncio.Event()

    class TrackingSession(FakeSession):
        def make_request(self, request: Request):
            call_times.append(asyncio.get_event_loop().time())
            return super().make_request(request)

    async def callback(response: Response, request: Request):
        seen.append(response.url)
        if len(seen) == 2:
            finished.set()

    manager = base_manager_factory(
        session_factory=TrackingSession,
        default_interval=default_interval,
    )

    await manager.sender(Request(url="https://api.test.com/first", callback=callback))
    await manager.sender(Request(url="https://api.test.com/second", callback=callback))

    await asyncio.wait_for(finished.wait(), timeout=1.0)
    await manager.wait()
    await manager.close()

    assert len(call_times) == 2

    elapsed = call_times[1] - call_times[0]
    # Allow small scheduling jitter when measuring asyncio sleep
    assert elapsed >= default_interval - 0.01


@pytest.mark.asyncio
async def test_raise_for_status_triggers_errback(base_manager_factory):
    """Test that HTTP errors trigger errback."""
    captured: dict[str, Any] = {}

    async def errback(exc: Exception, request: Request):
        captured["exc"] = exc
        captured["request"] = request

    manager = base_manager_factory(session_factory=lambda: FixedStatusSession(status=502, body="bad gateway"))

    await manager._send_request(attempt(Request(url="https://api.test.com/error", errback=errback)))

    assert isinstance(captured["exc"], HTTPException)
    assert captured["exc"].status_code == 502
    assert captured["exc"].message == "bad gateway"
    assert captured["request"].url == "https://api.test.com/error"


@pytest.mark.asyncio
async def test_sender_raises_on_data_and_json(base_manager_factory):
    """Test that sender raises InvalidRequestData when both data and json_data are provided."""
    manager = base_manager_factory(session_factory=NoopSession)

    with pytest.raises(InvalidRequestData, match="data and json_data"):
        await manager.sender(
            Request(
                url="https://api.test.com/bad",
                method="POST",
                data={"x": 1},
                json_data={"y": 2},
            ),
        )

    await manager.close()


@pytest.mark.asyncio
async def test_sender_raises_on_files_and_json(base_manager_factory):
    """Test that sender raises InvalidRequestData when both files and json_data are provided."""
    manager = base_manager_factory(session_factory=NoopSession)

    with pytest.raises(InvalidRequestData, match="files and json_data"):
        await manager.sender(
            Request(
                url="https://api.test.com/bad",
                method="POST",
                files={"file": File("name", b"content")},
                json_data={"y": 2},
            ),
        )

    await manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["auth", "proxy_auth"])
async def test_sender_raises_on_an_unknown_credentials_encoding(base_manager_factory, field: str):
    """A codec that does not exist is a broken request, not a backend limitation."""
    manager = base_manager_factory(session_factory=NoopSession)

    request = Request(url="https://api.test.com/bad")
    setattr(request, field, {"username": "user", "encoding": "not-a-real-codec"})

    with pytest.raises(InvalidRequestData, match=f"Unknown {field} encoding: not-a-real-codec"):
        await manager.sender(request)

    await manager.close()


@pytest.mark.asyncio
async def test_sender_accepts_a_known_credentials_encoding(base_manager_factory):
    manager = base_manager_factory(session_factory=NoopSession)

    await manager.sender(Request(url="https://api.test.com/ok", auth={"username": "user", "encoding": "latin1"}))

    await manager.close()


@pytest.mark.asyncio
async def test_dispatch_rejects_what_a_middleware_broke():
    """A middleware owns the request until dispatch, so validation cannot stop at send time."""

    def factory():
        async def middleware(call_next: RequestHandler, request: Request):
            request.auth = {"username": "user", "encoding": "not-a-real-codec"}
            return await call_next(request)

        return middleware

    middleware_holder = MiddlewareHolder()
    middleware_holder.add(factory)

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={},
        middleware_holder=middleware_holder,
    )
    manager.start_listening()
    errors: list[Exception] = []

    async def errback(exc: Exception):
        errors.append(exc)

    await manager._send_request(attempt(Request(url="https://api.test.com/test", errback=errback)))

    assert [type(error) for error in errors] == [InvalidRequestData]
    assert "not-a-real-codec" in str(errors[0])

    await manager.close()


@pytest.mark.asyncio
async def test_callback_receives_cb_kwargs(base_manager_factory):
    """Test that callback receives cb_kwargs."""
    captured = {}

    async def callback(response: Response, custom_arg: str):
        captured["response"] = response
        captured["custom_arg"] = custom_arg

    manager = base_manager_factory(session_factory=FakeSession)

    await manager._send_request(
        attempt(
            Request(url="https://api.test.com/test", callback=callback, cb_kwargs={"custom_arg": "test_value"}),
        )
    )

    assert "response" in captured
    assert captured["custom_arg"] == "test_value"


@pytest.mark.asyncio
async def test_dependencies_injected_into_callback():
    """Test that dependencies are injected into callback."""
    captured = {}

    async def callback(response: Response, custom_dep: str):
        captured["response"] = response
        captured["custom_dep"] = custom_dep

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={"custom_dep": "injected_value"},
        middleware_holder=MiddlewareHolder(),
    )
    manager.start_listening()

    await manager._send_request(attempt(Request(url="https://api.test.com/test", callback=callback)))

    assert "response" in captured
    assert captured["custom_dep"] == "injected_value"

    await manager.close()


@pytest.mark.asyncio
async def test_dependencies_injected_into_middleware():
    """Test that dependencies are injected into middleware factories."""
    captured = {}

    def factory(custom_dep: str):
        captured["custom_dep"] = custom_dep

        async def middleware(call_next: RequestHandler, request: Request):
            captured["request"] = request
            return await call_next(request)

        return middleware

    middleware_holder = MiddlewareHolder()
    middleware_holder.add(factory)

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={"custom_dep": "middleware_value"},
        middleware_holder=middleware_holder,
    )
    manager.start_listening()

    await manager._send_request(attempt(Request(url="https://api.test.com/test")))

    assert "request" in captured
    assert captured["custom_dep"] == "middleware_value"

    await manager.close()


@pytest.mark.asyncio
async def test_schedule_request_available_in_dependencies():
    """Test that schedule_request is available in dependencies, under its deprecated name too."""
    captured = {}

    async def callback(response: Response, schedule_request, send_request):
        captured["response"] = response
        captured["schedule_request"] = schedule_request
        captured["send_request"] = send_request

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    manager.start_listening()

    await manager._send_request(attempt(Request(url="https://api.test.com/test", callback=callback)))

    assert "response" in captured
    # Callbacks get the job sender, which skips the pending limit; manager.sender waits on it.
    assert captured["schedule_request"] is manager._job_sender
    assert captured["schedule_request"] is not manager.sender
    assert captured["send_request"] is captured["schedule_request"]

    await manager.close()


@pytest.mark.asyncio
async def test_queue_processes_requests():
    """Test that queue processes requests correctly."""
    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(per_group=False, default_interval=0.05),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    manager.start_listening()

    assert manager._ready_queue.empty()

    await manager.sender(Request(url="https://api.test.com/test"))

    # Queue should have items
    assert not manager._ready_queue.empty()

    # Get item from queue
    await manager._ready_queue.get()

    # Queue should be empty again
    assert manager._ready_queue.empty()

    await manager.close()


@pytest.mark.asyncio
async def test_exception_logged_when_no_errback(caplog):
    """Test that exception is logged when errback is not provided."""
    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=lambda: FixedStatusSession(status=500, body="server error"),
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    manager.start_listening()

    # Should not raise, just log
    await manager._send_request(attempt(Request(url="https://api.test.com/test")))

    # Verify that error was logged
    assert any("https://api.test.com/test" in record.message for record in caplog.records)
    assert any(record.levelname == "ERROR" for record in caplog.records)

    await manager.close()


@pytest.mark.asyncio
async def test_url_with_params_is_parsed():
    """Test that URL with params is correctly parsed."""
    captured = {}

    async def callback(response: Response):
        captured["url"] = response.url

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    manager.start_listening()

    await manager._send_request(
        attempt(
            Request(url="https://api.test.com/test", params={"key": "value", "foo": "bar"}, callback=callback),
        )
    )

    # URL should contain query params
    assert "url" in captured

    await manager.close()


def _adaptive_rate_limit_config() -> RateLimitConfig:
    return RateLimitConfig(
        per_group=True,
        default_interval=0.05,
        adaptive=AdaptiveRateLimitConfig(min_interval=0.001, max_interval=1.0, increase_factor=2.0),
    )


def _spy_on_outcomes(manager: RequestManager) -> list[RequestOutcome]:
    outcomes: list[RequestOutcome] = []
    on_request_outcome = manager._rate_limiter_manager.on_request_outcome

    def spy(outcome: RequestOutcome):
        outcomes.append(outcome)
        on_request_outcome(outcome)

    manager._rate_limiter_manager.on_request_outcome = spy  # type: ignore[reportAttributeAccessIssue]
    return outcomes


def _spy_on_retries(manager: RequestManager) -> asyncio.Event:
    "Fires once a failure has been re-admitted; the outcome is recorded before that."
    retried = asyncio.Event()
    retry = manager._retry

    async def spy(attempt: Attempt, exc: Exception) -> bool:
        result = await retry(attempt, exc)
        retried.set()
        return result

    manager._retry = spy  # type: ignore[reportAttributeAccessIssue]
    return retried


@pytest.mark.asyncio
async def test_retried_request_is_reported_to_adaptive_limiter():
    """A 503 swallowed by the retry policy must still be seen as a failure."""
    retry_config = RequestRetryConfig(
        enabled=True,
        attempts=3,
        backoff=BackoffStrategy.CONSTANT,
        base_delay=10.0,
    )

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=_adaptive_rate_limit_config(),
        retry_config=retry_config,
        shutdown_check_interval=0.01,
        sessionmaker=lambda: FixedStatusSession(status=503, body="unavailable"),
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    manager.start_listening()
    outcomes = _spy_on_outcomes(manager)
    retried = _spy_on_retries(manager)

    try:
        # base_delay=10s keeps the retry parked in the heap: exactly one attempt runs.
        await manager.sender(Request(url="https://api.test.com/flaky"))
        await asyncio.wait_for(retried.wait(), timeout=5.0)

        assert len(outcomes) == 1
        assert outcomes[0].status_code == 503
        assert outcomes[0].exception_type is HTTPException

        # default_interval * increase_factor
        group = manager._rate_limiter_manager._groups["api.test.com"]
        assert group.interval == pytest.approx(0.1)
    finally:
        # Drop the parked retry so the listener drains instead of waiting 10s.
        manager._delayed_heap.clear()
        await asyncio.wait_for(manager.shutdown(), timeout=5.0)
        await manager.close()

    assert manager._task is not None
    assert manager._task.done()
    assert not manager._delayed_heap


@pytest.mark.asyncio
async def test_unsupported_option_reaches_errback_without_an_outcome():
    """A backend rejecting the request is a contract error, not a transport outcome."""
    captured: dict[str, Any] = {}

    async def errback(exc: Exception, request: Request):
        captured["exc"] = exc
        captured["request"] = request

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=_adaptive_rate_limit_config(),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=lambda: HttpxSession(timeout=1.0, verify=True, proxy=None),
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    outcomes = _spy_on_outcomes(manager)

    await manager._send_request(
        attempt(
            Request(url="https://api.test.com/resource", proxy="http://proxy:8080", errback=errback),
        )
    )

    assert isinstance(captured["exc"], UnsupportedRequestOption)
    assert captured["exc"].option == "proxy"
    assert captured["request"].url == "https://api.test.com/resource"

    # Recording it would count as a success and shrink the interval for a request never sent.
    assert outcomes == []

    await manager.close()


@pytest.mark.asyncio
async def test_outcome_goes_to_the_group_that_paced_the_request():
    """A middleware rewriting the host must not move the outcome to another group."""

    def rewrite_host():
        async def middleware(call_next: RequestHandler, request: Request) -> Response | None:
            return await call_next(replace(request, url="https://rewritten.test.com/ok"))

        return middleware

    middleware_holder = MiddlewareHolder()
    middleware_holder.add(rewrite_host)

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=_adaptive_rate_limit_config(),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={},
        middleware_holder=middleware_holder,
    )
    outcomes = _spy_on_outcomes(manager)

    await manager._send_request(attempt(Request(url="https://api.test.com/ok")))

    assert [outcome.group_key for outcome in outcomes] == ["api.test.com"]

    await manager.close()


@pytest.mark.asyncio
async def test_none_is_a_group_key_like_any_other():
    """None is Hashable, so a group_by may return it and its outcomes must still arrive."""
    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=_adaptive_rate_limit_config(),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
        group_by=lambda request: GroupPolicy(None, 0.001),
    )
    outcomes = _spy_on_outcomes(manager)
    manager.start_listening()

    await manager.sender(Request(url="https://api.test.com/ok"))
    await asyncio.wait_for(manager.wait(), timeout=5.0)

    assert [outcome.group_key for outcome in outcomes] == [None]

    await manager.close()


@pytest.mark.asyncio
async def test_callback_failure_is_not_reported_as_transport_failure():
    """Callback errors must not reach the adaptive limiter as request outcomes."""

    async def callback(response: Response):
        # a trigger type, so the outcome below is missing because it was never recorded
        raise TransportTimeout("https://api.test.com/ok", "GET", "callback boom")

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=_adaptive_rate_limit_config(),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    outcomes = _spy_on_outcomes(manager)

    assert manager._rate_limiter_manager.adaptive_strategy is not None
    assert TransportTimeout in manager._rate_limiter_manager.adaptive_strategy.trigger_exceptions

    await manager._send_request(attempt(Request(url="https://api.test.com/ok", callback=callback)))

    assert len(outcomes) == 1
    assert outcomes[0].status_code == 200
    assert outcomes[0].exception_type is None

    await manager.close()


@pytest.mark.asyncio
async def test_errback_failure_is_not_reported_as_transport_failure():
    """A failing errback must not reach the adaptive limiter either."""

    async def callback(response: Response):
        raise TimeoutError("callback boom")

    async def errback(exc: Exception):
        raise ValueError("errback boom")

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=_adaptive_rate_limit_config(),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    outcomes = _spy_on_outcomes(manager)

    with pytest.raises(ExceptionGroup) as excinfo:
        await manager._send_request(attempt(Request(url="https://api.test.com/ok", callback=callback, errback=errback)))

    assert isinstance(excinfo.value.exceptions[0], TimeoutError)
    assert isinstance(excinfo.value.exceptions[1], ValueError)

    assert len(outcomes) == 1
    assert outcomes[0].status_code == 200
    assert outcomes[0].exception_type is None

    await manager.close()


@pytest.mark.asyncio
async def test_next_timeout_uses_shutdown_check_interval(base_manager_factory):
    """The queue poll timeout comes from shutdown_check_interval, not a constant."""
    manager = base_manager_factory(session_factory=FakeSession)

    assert not manager._delayed_heap
    assert manager._next_timeout() == 0.01

    await manager.close()


@pytest.mark.asyncio
async def test_shutdown_is_not_delayed_by_a_parked_request(base_manager_factory):
    """A long delay must not become the poll timeout: the listener would keep waiting on a
    deadline that no longer has an entry behind it."""
    manager = base_manager_factory(session_factory=FakeSession)

    await manager.sender(Request(url="https://api.test.com/1", delay=30.0))
    # Let the listener reach the wait while the entry is still in the heap.
    await asyncio.sleep(0.05)

    manager._delayed_heap.clear()
    await asyncio.wait_for(manager.shutdown(), timeout=2.0)

    await manager.close()


@pytest.mark.asyncio
async def test_close_stops_queue_processing():
    """Test that close stops queue processing."""
    calls = []
    finished = asyncio.Event()

    async def callback(response: Response):
        calls.append("callback")
        finished.set()

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    manager.start_listening()

    await manager.sender(Request(url="https://api.test.com/test", callback=callback))
    await asyncio.wait_for(finished.wait(), timeout=1.0)

    await manager.wait()
    await manager.close()

    # Session should be closed
    assert manager._session.closed is True  # type: ignore[reportAttributeAccessIssue]
    assert manager._task is not None
    assert manager._task.done()


@pytest.mark.asyncio
async def test_a_retry_that_never_reached_the_queue_is_not_counted(base_manager_factory, monkeypatch):
    """The counter is about attempts that were admitted, not about the decision to admit one."""
    manager = base_manager_factory(session_factory=FakeSession)
    manager._retry_policy = RetryPolicy(RequestRetryConfig(enabled=True, attempts=3, base_delay=0.001))

    async def failing_admit(*args, **kwargs):
        raise asyncio.CancelledError

    monkeypatch.setattr("aioscraper.core.request_manager._admit", failing_admit)

    with pytest.raises(asyncio.CancelledError):
        await manager._retry(attempt(Request(url="https://api.test.com/flaky")), _http_error())

    assert manager._stats.requests_retried == 0

    await manager.close()


def _idle_manager(**kwargs: Any) -> RequestManager:
    "Listener not started, so the queues hold still."
    return RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
        **kwargs,
    )


class SlowRequestContextManager(BaseRequestContextManager):
    async def __aenter__(self) -> Response:
        await asyncio.sleep(0.002)
        return make_response(url=self._request.url, method=self._request.method, headers={})


class SlowSession(BaseSession):
    def make_request(self, request: Request) -> SlowRequestContextManager:
        return SlowRequestContextManager(request)

    async def _close_client(self):
        pass


@pytest.mark.asyncio
async def test_a_due_delayed_request_competes_by_its_own_priority():
    sent: list[str] = []
    delayed_sent = asyncio.Event()

    async def callback(request: Request):
        sent.append(request.url)
        if request.url.endswith("/delayed"):
            delayed_sent.set()

    manager = RequestManager(
        scheduler_config=SchedulerConfig(concurrent_requests=1),
        rate_limit_config=RateLimitConfig(),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=SlowSession,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    manager.start_listening()

    async def produce():
        # outpaces the single slot
        for i in range(2000):
            if delayed_sent.is_set():
                return

            await manager.sender(Request(url=f"https://api.test.com/{i}", callback=callback))
            await asyncio.sleep(0.0005)

        pytest.fail("the delayed request starved behind the producer")

    try:
        await manager.sender(Request(url="https://api.test.com/delayed", delay=0.05, priority=-1, callback=callback))
        await asyncio.wait_for(produce(), timeout=10.0)
    finally:
        manager._ready_queue = asyncio.PriorityQueue()
        await manager.close()

    assert "https://api.test.com/delayed" in sent


@pytest.mark.asyncio
async def test_pop_due_delayed_restores_the_request_priority():
    manager = _idle_manager()
    request = Request(url="https://api.test.com/delayed", priority=-100)
    manager._delayed_heap.append(Attempt(priority=0.0, request=request))
    manager._ready_queue.put_nowait(Attempt(priority=0, request=Request(url="https://api.test.com/normal")))

    await manager._pop_due_delayed()

    first = manager._ready_queue.get_nowait()
    assert first.request is request
    assert first.priority == -100

    await manager.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("delay", [math.nan, math.inf, -math.inf, -1.0])
async def test_a_delay_that_never_comes_due_is_rejected(delay: float):
    manager = _idle_manager()

    with pytest.raises(InvalidRequestData, match="delay"):
        await manager.sender(Request(url="https://api.test.com/x", delay=delay))

    assert not manager._delayed_heap
    assert manager._ready_queue.empty()
    await manager.close()


@pytest.mark.asyncio
async def test_a_zero_delay_queues_the_request_ready():
    manager = _idle_manager()

    await manager.sender(Request(url="https://api.test.com/x", delay=0))

    assert not manager._delayed_heap
    assert manager._ready_queue.qsize() == 1
    await manager.close()


def _broken_group_by(request: Request) -> GroupPolicy:
    raise ValueError("broken grouping")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("group_by", "message"),
    [
        (_broken_group_by, "group_by failed"),
        (lambda request: ("key", 0.1), "must return"),
        (lambda request: None, "must return"),
        (lambda request: ([], 0.1, None), "must return"),
        (lambda request: ("key", math.nan, None), "invalid interval"),
        (lambda request: ("key", math.inf, None), "invalid interval"),
        (lambda request: ("key", "0.1", None), "invalid interval"),
        (lambda request: ("key", 0.1, "3"), "invalid concurrency"),
        (lambda request: ("key", 0.1, 2.5), "invalid concurrency"),
    ],
    ids=[
        "raises",
        "short-tuple",
        "not-a-tuple",
        "unhashable-key",
        "nan",
        "inf",
        "str-interval",
        "str-ceiling",
        "float-ceiling",
    ],
)
async def test_a_broken_group_by_fails_the_wait_instead_of_hanging(group_by: Any, message: str):
    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(per_group=True),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
        group_by=group_by,
    )
    manager.start_listening()

    try:
        await manager.sender(Request(url="https://api.test.com/x"))
        with pytest.raises(AIOScraperException, match=message):
            await asyncio.wait_for(manager.wait(), timeout=5.0)
    finally:
        await manager.close()


@pytest.mark.asyncio
async def test_a_failing_group_by_keeps_its_cause():
    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(per_group=True),
        retry_config=NO_RETRIES,
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
        group_by=_broken_group_by,
    )
    manager.start_listening()

    try:
        await manager.sender(Request(url="https://api.test.com/x"))
        with pytest.raises(AIOScraperException) as exc_info:
            await asyncio.wait_for(manager.wait(), timeout=5.0)
    finally:
        await manager.close()

    assert isinstance(exc_info.value.__cause__, ValueError)


def test_a_failing_middleware_factory_leaves_no_session():
    sessions: list[FakeSession] = []

    def sessionmaker() -> FakeSession:
        sessions.append(FakeSession())
        return sessions[-1]

    def broken_factory() -> RequestMiddleware:
        raise ValueError("broken middleware")

    holder = MiddlewareHolder()
    holder.add(broken_factory)

    with pytest.raises(AIOScraperException, match="Failed to instantiate"):
        RequestManager(
            scheduler_config=SchedulerConfig(),
            rate_limit_config=RateLimitConfig(),
            retry_config=NO_RETRIES,
            shutdown_check_interval=0.01,
            sessionmaker=sessionmaker,
            dependencies={},
            middleware_holder=holder,
        )

    assert sessions == []
