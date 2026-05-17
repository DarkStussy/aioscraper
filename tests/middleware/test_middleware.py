from typing import Callable

import pytest

from aioscraper.exceptions import HTTPException
from aioscraper.types import (
    Request,
    RequestHandler,
    RequestMiddleware,
    RequestMiddlewareFactory,
    Response,
    SendRequest,
)
from tests.mocks import MockAIOScraper, MockResponse


class MiddlewareScraper:
    def __init__(self):
        self.response: dict | None = None
        self.before: bool | None = None
        self.after_flag: bool | None = None
        self.exception_seen: bool = False

    async def __call__(self, send_request: SendRequest):
        await send_request(Request(url="https://api.test.com/v1", callback=self.parse))
        await send_request(Request(url="https://api.test.com/error", errback=self.handle_error))

    async def parse(self, response: Response, request: Request, before: bool):
        self.response = await response.json()
        self.before = before
        self.after_flag = request.state.get("after")

    async def handle_error(self, exc: Exception):
        self.exception_seen = isinstance(exc, HTTPException)


def register_via_decorator(scraper: MockAIOScraper, factory: RequestMiddlewareFactory):
    scraper.middleware(factory)


def register_via_add(scraper: MockAIOScraper, factory: RequestMiddlewareFactory):
    scraper.middleware.add(factory)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "register",
    [
        pytest.param(register_via_decorator, id="decorator"),
        pytest.param(register_via_add, id="add"),
    ],
)
async def test_middleware(
    mock_aioscraper: MockAIOScraper,
    register: Callable[[MockAIOScraper, RequestMiddlewareFactory], None],
):
    mock_aioscraper.server.add("https://api.test.com/v1", handler=lambda _: {"status": "OK"})
    mock_aioscraper.server.add("https://api.test.com/error", handler=lambda _: MockResponse(status=500))

    calls = {"before": 0, "after": 0, "exception": 0}

    def factory() -> RequestMiddleware:
        async def middleware(call_next: RequestHandler, request: Request) -> Response | None:
            calls["before"] += 1
            request.cb_kwargs["before"] = True
            try:
                response = await call_next(request)
            except HTTPException:
                calls["exception"] += 1
                raise
            calls["after"] += 1
            request.state["after"] = True
            return response

        return middleware

    register(mock_aioscraper, factory)

    scraper = MiddlewareScraper()
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    mock_aioscraper.server.assert_all_routes_handled()

    assert scraper.response == {"status": "OK"}
    assert scraper.before is True
    assert scraper.after_flag is True
    assert scraper.exception_seen is True
    assert calls == {"before": 2, "after": 1, "exception": 1}


@pytest.mark.asyncio
async def test_middleware_registration_order_controls_wrapping(mock_aioscraper: MockAIOScraper):
    """First registered middleware is the outermost wrapper."""
    mock_aioscraper.server.add("https://api.test.com/v1", handler=lambda _: {"status": "OK"})

    order: list[str] = []

    def outer_factory() -> RequestMiddleware:
        async def middleware(call_next: RequestHandler, request: Request) -> Response | None:
            order.append("outer-before")
            response = await call_next(request)
            order.append("outer-after")
            return response

        return middleware

    def inner_factory() -> RequestMiddleware:
        async def middleware(call_next: RequestHandler, request: Request) -> Response | None:
            order.append("inner-before")
            response = await call_next(request)
            order.append("inner-after")
            return response

        return middleware

    mock_aioscraper.middleware.add(outer_factory)
    mock_aioscraper.middleware.add(inner_factory)

    async def scrape(send_request: SendRequest):
        await send_request(Request(url="https://api.test.com/v1", callback=handle))

    async def handle():
        return None

    mock_aioscraper(scrape)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert order == ["outer-before", "inner-before", "inner-after", "outer-after"]


@pytest.mark.asyncio
async def test_middleware_short_circuit_skips_dispatch_and_callback(mock_aioscraper: MockAIOScraper):
    """Middleware that returns without calling call_next short-circuits dispatch and callback."""
    mock_aioscraper.server.add("https://api.test.com/v1", handler=lambda _: {"status": "OK"})

    calls: list[str] = []

    def factory() -> RequestMiddleware:
        async def middleware(call_next: RequestHandler, request: Request) -> Response | None:
            calls.append("middleware")
            return None

        return middleware

    mock_aioscraper.middleware.add(factory)

    async def scrape(send_request: SendRequest):
        await send_request(Request(url="https://api.test.com/v1", callback=callback))

    async def callback():
        calls.append("callback")

    mock_aioscraper(scrape)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert calls == ["middleware"]


@pytest.mark.asyncio
async def test_middleware_catches_exception_skips_errback(mock_aioscraper: MockAIOScraper):
    """Middleware that catches the exception and returns None should skip the errback."""
    mock_aioscraper.server.add("https://api.test.com/error", handler=lambda _: MockResponse(status=500))

    calls: list[str] = []

    def factory() -> RequestMiddleware:
        async def middleware(call_next: RequestHandler, request: Request) -> Response | None:
            try:
                return await call_next(request)
            except HTTPException:
                calls.append("caught")
                return None

        return middleware

    mock_aioscraper.middleware.add(factory)

    async def scrape(send_request: SendRequest):
        await send_request(Request(url="https://api.test.com/error", errback=errback))

    async def errback(exc: Exception):
        calls.append("errback")

    mock_aioscraper(scrape)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    mock_aioscraper.server.assert_all_routes_handled()

    assert calls == ["caught"]


@pytest.mark.asyncio
async def test_middleware_reads_response_body_lazily_after_call_next(mock_aioscraper: MockAIOScraper):
    """Middleware can consume the response body after ``call_next`` returns.

    The response context manager is kept open by the per-request AsyncExitStack
    until the whole chain unwinds, so body reads work even though dispatch has
    already returned.
    """
    mock_aioscraper.server.add("https://api.test.com/v1", handler=lambda _: {"status": "OK"})

    captured: dict[str, object] = {}

    def factory() -> RequestMiddleware:
        async def middleware(call_next: RequestHandler, request: Request) -> Response | None:
            response = await call_next(request)
            assert response is not None
            captured["status"] = response.status
            captured["body"] = await response.json()
            return response

        return middleware

    mock_aioscraper.middleware.add(factory)

    async def scrape(send_request: SendRequest):
        await send_request(Request(url="https://api.test.com/v1", callback=callback))

    async def callback(): ...

    mock_aioscraper(scrape)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    mock_aioscraper.server.assert_all_routes_handled()

    assert captured == {"status": 200, "body": {"status": "OK"}}


@pytest.mark.asyncio
async def test_outer_middleware_catches_inner_exception(mock_aioscraper: MockAIOScraper):
    """Outer middleware can catch an exception raised by an inner middleware (or dispatch)."""
    mock_aioscraper.server.add("https://api.test.com/error", handler=lambda _: MockResponse(status=500))

    calls: list[str] = []

    def outer_factory() -> RequestMiddleware:
        async def middleware(call_next: RequestHandler, request: Request) -> Response | None:
            try:
                return await call_next(request)
            except HTTPException:
                calls.append("outer-caught")
                return None

        return middleware

    def inner_factory() -> RequestMiddleware:
        async def middleware(call_next: RequestHandler, request: Request) -> Response | None:
            calls.append("inner-before")
            try:
                return await call_next(request)
            except HTTPException:
                calls.append("inner-rethrow")
                raise

        return middleware

    mock_aioscraper.middleware.add(outer_factory)
    mock_aioscraper.middleware.add(inner_factory)

    async def scrape(send_request: SendRequest):
        await send_request(Request(url="https://api.test.com/error", errback=errback))

    async def errback(exc: Exception):
        calls.append("errback")

    mock_aioscraper(scrape)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    mock_aioscraper.server.assert_all_routes_handled()

    assert calls == ["inner-before", "inner-rethrow", "outer-caught"]


@pytest.mark.asyncio
async def test_inner_middleware_short_circuit_propagates_none_to_outer(mock_aioscraper: MockAIOScraper):
    """When an inner middleware returns ``None``, the outer sees ``None`` from ``call_next``."""
    mock_aioscraper.server.add("https://api.test.com/v1", handler=lambda _: {"status": "OK"})

    calls: list[str] = []
    received: dict[str, Response | None] = {}

    def outer_factory() -> RequestMiddleware:
        async def middleware(call_next: RequestHandler, request: Request) -> Response | None:
            calls.append("outer-before")
            response = await call_next(request)
            calls.append("outer-after")
            received["response"] = response
            return response

        return middleware

    def inner_factory() -> RequestMiddleware:
        async def middleware(call_next: RequestHandler, request: Request) -> Response | None:
            calls.append("inner-short-circuit")
            return None

        return middleware

    mock_aioscraper.middleware.add(outer_factory)
    mock_aioscraper.middleware.add(inner_factory)

    async def scrape(send_request: SendRequest):
        await send_request(Request(url="https://api.test.com/v1", callback=callback))

    async def callback():
        calls.append("callback")

    mock_aioscraper(scrape)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert calls == ["outer-before", "inner-short-circuit", "outer-after"]
    assert received["response"] is None


@pytest.mark.asyncio
async def test_middleware_factory_receives_dependencies(mock_aioscraper: MockAIOScraper):
    """Middleware factories receive injected dependencies via parameter names."""
    mock_aioscraper.server.add("https://api.test.com/v1", handler=lambda _: {"status": "OK"})

    captured: dict = {}

    def factory(send_request: SendRequest, custom_dep: str) -> RequestMiddleware:
        captured["custom_dep"] = custom_dep
        captured["send_request"] = send_request

        async def middleware(call_next: RequestHandler, request: Request) -> Response | None:
            return await call_next(request)

        return middleware

    mock_aioscraper.add_dependencies(custom_dep="injected")
    mock_aioscraper.middleware.add(factory)

    async def scrape(send_request: SendRequest):
        await send_request(Request(url="https://api.test.com/v1", callback=callback))

    async def callback(): ...

    mock_aioscraper(scrape)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert captured["custom_dep"] == "injected"
    assert callable(captured["send_request"])
