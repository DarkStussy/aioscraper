import asyncio
from http.cookies import SimpleCookie
from typing import Any

import pytest

from aioscraper.config import (
    AdaptiveRateLimitConfig,
    BackoffStrategy,
    RateLimitConfig,
    RequestRetryConfig,
    SchedulerConfig,
)
from aioscraper.core.rate_limiter import RequestOutcome
from aioscraper.core.request_manager import RequestManager
from aioscraper.core.session import BaseRequestContextManager, BaseSession
from aioscraper.core.session.httpx import HttpxSession
from aioscraper.exceptions import HTTPException, InvalidRequestData, UnsupportedRequestOption
from aioscraper.holders import MiddlewareHolder
from aioscraper.middlewares import RetryMiddleware
from aioscraper.types import File, Request, RequestHandler, Response, SendRequest


async def _read() -> bytes:
    return b""


class FakeRequestContextManager(BaseRequestContextManager):
    async def __aenter__(self) -> Response:
        return Response(
            url=self._request.url,
            method=self._request.method,
            status=200,
            headers={},
            cookies=SimpleCookie(),
            read=_read,
        )


class FakeSession(BaseSession):
    def __init__(self):
        self.closed = False
        self.calls = 0

    def make_request(self, request: Request) -> FakeRequestContextManager:
        return FakeRequestContextManager(request)

    async def close(self):
        self.closed = True


def _build_response(request: Request, *, status: int, body: str = "") -> Response:
    body_bytes = body.encode()

    async def _read() -> bytes:
        return body_bytes

    return Response(
        url=request.url,
        method=request.method,
        status=status,
        headers={"Content-Type": "text/plain; charset=utf-8"},
        cookies=SimpleCookie(),
        read=_read,
    )


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

    async def close(self): ...


class NoopSession(BaseSession):
    def make_request(self, request: Request) -> BaseRequestContextManager:
        raise AssertionError("should not be called when validation fails")

    async def close(self): ...


@pytest.fixture
def middleware_holder() -> MiddlewareHolder:
    return MiddlewareHolder()


@pytest.fixture
def base_manager_factory(middleware_holder: MiddlewareHolder):
    def factory(*, session_factory, default_interval=0.0):
        manager = RequestManager(
            scheduler_config=SchedulerConfig(),
            rate_limit_config=RateLimitConfig(default_interval=default_interval),
            retry_config=RequestRetryConfig(),
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
        retry_config=RequestRetryConfig(),
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

    await manager._send_request(Request(url="https://api.test.com/error", errback=errback))

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
async def test_callback_receives_cb_kwargs(base_manager_factory):
    """Test that callback receives cb_kwargs."""
    captured = {}

    async def callback(response: Response, custom_arg: str):
        captured["response"] = response
        captured["custom_arg"] = custom_arg

    manager = base_manager_factory(session_factory=FakeSession)

    await manager._send_request(
        Request(url="https://api.test.com/test", callback=callback, cb_kwargs={"custom_arg": "test_value"}),
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
        retry_config=RequestRetryConfig(),
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={"custom_dep": "injected_value"},
        middleware_holder=MiddlewareHolder(),
    )
    manager.start_listening()

    await manager._send_request(Request(url="https://api.test.com/test", callback=callback))

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
        retry_config=RequestRetryConfig(),
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={"custom_dep": "middleware_value"},
        middleware_holder=middleware_holder,
    )
    manager.start_listening()

    await manager._send_request(Request(url="https://api.test.com/test"))

    assert "request" in captured
    assert captured["custom_dep"] == "middleware_value"

    await manager.close()


@pytest.mark.asyncio
async def test_send_request_available_in_dependencies():
    """Test that send_request is available in dependencies."""
    captured = {}

    async def callback(response: Response, send_request):
        captured["response"] = response
        captured["send_request"] = send_request

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(),
        retry_config=RequestRetryConfig(),
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    manager.start_listening()

    await manager._send_request(Request(url="https://api.test.com/test", callback=callback))

    assert "response" in captured
    # Callbacks get the job sender, which skips the pending limit; manager.sender waits on it.
    assert captured["send_request"] is manager._job_sender
    assert captured["send_request"] is not manager.sender

    await manager.close()


@pytest.mark.asyncio
async def test_queue_processes_requests():
    """Test that queue processes requests correctly."""
    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(enabled=False, default_interval=0.05),
        retry_config=RequestRetryConfig(),
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
        retry_config=RequestRetryConfig(),
        shutdown_check_interval=0.01,
        sessionmaker=lambda: FixedStatusSession(status=500, body="server error"),
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    manager.start_listening()

    # Should not raise, just log
    await manager._send_request(Request(url="https://api.test.com/test"))

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
        retry_config=RequestRetryConfig(),
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    manager.start_listening()

    await manager._send_request(
        Request(url="https://api.test.com/test", params={"key": "value", "foo": "bar"}, callback=callback),
    )

    # URL should contain query params
    assert "url" in captured

    await manager.close()


def _adaptive_rate_limit_config() -> RateLimitConfig:
    return RateLimitConfig(
        enabled=True,
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


@pytest.mark.asyncio
async def test_retried_request_is_reported_to_adaptive_limiter():
    """A 503 swallowed by the retry middleware must still be seen as a failure."""
    retried = asyncio.Event()
    retry_config = RequestRetryConfig(
        enabled=True,
        attempts=3,
        backoff=BackoffStrategy.CONSTANT,
        base_delay=10.0,
    )
    middleware_holder = MiddlewareHolder()

    def retry_factory(send_request: SendRequest) -> RetryMiddleware:
        # Fires when the retry is re-queued; the outcome is recorded before that.
        async def tracking_sender(request: Request) -> Request:
            result = await send_request(request)
            retried.set()
            return result

        return RetryMiddleware(retry_config, tracking_sender)

    middleware_holder.add(retry_factory)

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=_adaptive_rate_limit_config(),
        retry_config=retry_config,
        shutdown_check_interval=0.01,
        sessionmaker=lambda: FixedStatusSession(status=503, body="unavailable"),
        dependencies={},
        middleware_holder=middleware_holder,
    )
    manager.start_listening()
    outcomes = _spy_on_outcomes(manager)

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

    assert manager._completed.is_set()
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
        retry_config=RequestRetryConfig(),
        shutdown_check_interval=0.01,
        sessionmaker=lambda: HttpxSession(timeout=1.0, verify=True, proxy=None),
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    outcomes = _spy_on_outcomes(manager)

    await manager._send_request(
        Request(url="https://api.test.com/resource", proxy="http://proxy:8080", errback=errback),
    )

    assert isinstance(captured["exc"], UnsupportedRequestOption)
    assert captured["exc"].option == "proxy"
    assert captured["request"].url == "https://api.test.com/resource"

    # Recording it would count as a success and shrink the interval for a request never sent.
    assert outcomes == []

    await manager.close()


@pytest.mark.asyncio
async def test_callback_failure_is_not_reported_as_transport_failure():
    """Callback errors must not reach the adaptive limiter as request outcomes."""

    async def callback(response: Response):
        raise TimeoutError("callback boom")

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=_adaptive_rate_limit_config(),
        retry_config=RequestRetryConfig(),
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    outcomes = _spy_on_outcomes(manager)

    assert manager._rate_limiter_manager.adaptive_strategy is not None
    assert TimeoutError in manager._rate_limiter_manager.adaptive_strategy.trigger_exceptions

    await manager._send_request(Request(url="https://api.test.com/ok", callback=callback))

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
        retry_config=RequestRetryConfig(),
        shutdown_check_interval=0.01,
        sessionmaker=FakeSession,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    outcomes = _spy_on_outcomes(manager)

    with pytest.raises(ExceptionGroup) as excinfo:
        await manager._send_request(Request(url="https://api.test.com/ok", callback=callback, errback=errback))

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
        retry_config=RequestRetryConfig(),
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
    assert manager._completed.is_set()
