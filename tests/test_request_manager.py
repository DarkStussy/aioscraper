import asyncio
from http.cookies import SimpleCookie
from typing import Any

import pytest

from aioscraper.config import RateLimitConfig, RequestRetryConfig, SchedulerConfig
from aioscraper.core.request_manager import RequestManager
from aioscraper.core.session import BaseRequestContextManager, BaseSession
from aioscraper.exceptions import HTTPException, InvalidRequestData
from aioscraper.holders import MiddlewareHolder
from aioscraper.types import File, Request, Response


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
        sessionmaker=lambda: FakeSession(),
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
        session_factory=lambda: TrackingSession(),
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
    manager = base_manager_factory(session_factory=lambda: NoopSession())

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
    manager = base_manager_factory(session_factory=lambda: NoopSession())

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

    manager = base_manager_factory(session_factory=lambda: FakeSession())

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
        sessionmaker=lambda: FakeSession(),
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
    """Test that dependencies are injected into middleware."""
    captured = {}

    async def inner_middleware(request: Request, custom_dep: str):
        captured["request"] = request
        captured["custom_dep"] = custom_dep

    middleware_holder = MiddlewareHolder()
    middleware_holder.add("inner", inner_middleware)

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(),
        retry_config=RequestRetryConfig(),
        shutdown_check_interval=0.01,
        sessionmaker=lambda: FakeSession(),
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
        sessionmaker=lambda: FakeSession(),
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )
    manager.start_listening()

    await manager._send_request(Request(url="https://api.test.com/test", callback=callback))

    assert "response" in captured
    assert captured["send_request"] is manager.sender

    await manager.close()


@pytest.mark.asyncio
async def test_queue_processes_requests():
    """Test that queue processes requests correctly."""
    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(enabled=False, default_interval=0.05),
        retry_config=RequestRetryConfig(),
        shutdown_check_interval=0.01,
        sessionmaker=lambda: FakeSession(),
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
async def test_outer_middleware_execution_in_listen_queue():
    """Test that outer middleware is executed in listen_queue."""
    calls = []
    finished = asyncio.Event()

    async def outer_middleware(request: Request):
        calls.append(f"outer: {request.url}")

    async def callback(response: Response):
        calls.append(f"callback: {response.url}")
        finished.set()

    middleware_holder = MiddlewareHolder()
    middleware_holder.add("outer", outer_middleware)

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(),
        retry_config=RequestRetryConfig(),
        shutdown_check_interval=0.01,
        sessionmaker=lambda: FakeSession(),
        dependencies={},
        middleware_holder=middleware_holder,
    )
    manager.start_listening()

    await manager.sender(Request(url="https://api.test.com/test", callback=callback))

    await asyncio.wait_for(finished.wait(), timeout=1.0)
    await manager.wait()
    await manager.close()

    assert "outer: https://api.test.com/test" in calls
    assert "callback: https://api.test.com/test" in calls


@pytest.mark.asyncio
async def test_outer_middleware_exception_is_logged():
    """Test that exceptions in outer middleware are logged but don't stop processing."""
    calls = []
    finished = asyncio.Event()

    async def failing_outer_middleware(request: Request):
        calls.append("outer_called")
        raise RuntimeError("outer middleware failed")

    async def callback(response: Response):
        calls.append("callback_called")
        finished.set()

    middleware_holder = MiddlewareHolder()
    middleware_holder.add("outer", failing_outer_middleware)

    manager = RequestManager(
        scheduler_config=SchedulerConfig(),
        rate_limit_config=RateLimitConfig(),
        retry_config=RequestRetryConfig(),
        shutdown_check_interval=0.01,
        sessionmaker=lambda: FakeSession(),
        dependencies={},
        middleware_holder=middleware_holder,
    )
    manager.start_listening()

    await manager.sender(Request(url="https://api.test.com/test", callback=callback))

    await asyncio.wait_for(finished.wait(), timeout=1.0)
    await manager.wait()
    await manager.close()

    assert "outer_called" in calls
    assert "callback_called" in calls


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
        sessionmaker=lambda: FakeSession(),
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
        sessionmaker=lambda: FakeSession(),
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
