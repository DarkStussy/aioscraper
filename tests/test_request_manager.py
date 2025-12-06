import asyncio
from http.cookies import SimpleCookie

import pytest

from aioscraper.holders import MiddlewareHolder
from aioscraper.scraper.request_manager import RequestManager
from aioscraper.session.base import BaseSession
from aioscraper.types import Request, Response


class FakeSession(BaseSession):
    def __init__(self) -> None:
        self.closed = False
        self.calls = 0

    async def make_request(self, request: Request) -> Response:
        self.calls += 1
        return Response(
            url=request.url,
            method=request.method,
            status=200,
            headers={},
            cookies=SimpleCookie(),
            content=b"ok",
        )

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_errback_failure_wrapped_in_exception_group():
    async def errback(exc: Exception) -> None:
        raise ValueError("errback failed")

    manager = RequestManager(
        session=FakeSession(),
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

    async def callback(response: Response, request: Request) -> None:
        seen.append(response.url)
        if len(seen) == 2:
            finished.set()

    manager = RequestManager(
        session=FakeSession(),
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
