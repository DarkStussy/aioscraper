import asyncio
from http.cookies import SimpleCookie
from typing import Any

import pytest

from aioscraper.exceptions import HTTPException
from aioscraper.holders import MiddlewareHolder
from aioscraper.scraper.request_manager import RequestManager
from aioscraper.session.base import BaseSession, BaseRequestContextManager
from aioscraper.types import Request, Response


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

    async def close(self):  # pragma: no cover - nothing to clean up
        pass


@pytest.mark.asyncio
async def test_errback_failure_wrapped_in_exception_group():
    async def errback(exc: Exception):
        raise ValueError("errback failed")

    manager = RequestManager(
        sessionmaker=lambda: FakeSession(),
        schedule_request=lambda coro: coro,  # not used in this test
        queue=asyncio.PriorityQueue(),
        delay=0,
        shutdown_timeout=0.1,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )

    with pytest.raises(ExceptionGroup) as excinfo:
        await manager._handle_exception(
            Request(url="https://api.test.com/errback", errback=errback), RuntimeError("boom")
        )

    assert len(excinfo.value.exceptions) == 2
    assert isinstance(excinfo.value.exceptions[0], RuntimeError)
    assert isinstance(excinfo.value.exceptions[1], ValueError)


@pytest.mark.asyncio
async def test_request_manager_respects_delay_between_requests():
    call_times: list[float] = []
    seen: list[str] = []
    delay = 0.1
    finished = asyncio.Event()

    async def schedule_request(coro):
        call_times.append(asyncio.get_event_loop().time())
        await coro

    async def callback(response: Response, request: Request):
        seen.append(response.url)
        if len(seen) == 2:
            finished.set()

    manager = RequestManager(
        sessionmaker=lambda: FakeSession(),
        schedule_request=schedule_request,
        queue=asyncio.PriorityQueue(),
        delay=delay,
        shutdown_timeout=0.1,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )

    manager.listen_queue()

    await manager.sender(Request(url="https://api.test.com/first", callback=callback))
    await manager.sender(Request(url="https://api.test.com/second", callback=callback))

    await asyncio.wait_for(finished.wait(), timeout=1.0)
    await manager.close()

    assert len(call_times) == 2

    elapsed = call_times[1] - call_times[0]
    # Allow small scheduling jitter when measuring asyncio sleep
    assert elapsed >= delay - 0.01


@pytest.mark.asyncio
async def test_raise_for_status_triggers_errback_when_enabled():
    captured: dict[str, Any] = {}

    async def errback(exc: Exception, request: Request):
        captured["exc"] = exc
        captured["request"] = request

    manager = RequestManager(
        sessionmaker=lambda: FixedStatusSession(status=502, body="bad gateway"),
        schedule_request=lambda coro: coro,
        queue=asyncio.PriorityQueue(),
        delay=0,
        shutdown_timeout=0.1,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )

    await manager._send_request(Request(url="https://api.test.com/error", errback=errback))

    assert isinstance(captured["exc"], HTTPException)
    assert captured["exc"].status_code == 502
    assert captured["exc"].message == "bad gateway"
    assert captured["request"].url == "https://api.test.com/error"


@pytest.mark.asyncio
async def test_raise_for_status_false_skips_errback():
    called: dict[str, Any] = {"errback": False}

    async def callback(response: Response):
        called["response"] = response

    async def errback(exc: Exception, request: Request):
        called["errback"] = True

    manager = RequestManager(
        sessionmaker=lambda: FixedStatusSession(status=500, body="boom"),
        schedule_request=lambda coro: coro,
        queue=asyncio.PriorityQueue(),
        delay=0,
        shutdown_timeout=0.1,
        dependencies={},
        middleware_holder=MiddlewareHolder(),
    )

    await manager._send_request(
        Request(
            url="https://api.test.com/error",
            callback=callback,
            errback=errback,
            raise_for_status=False,
        )
    )

    assert called["response"].status == 500
    assert called["errback"] is False
