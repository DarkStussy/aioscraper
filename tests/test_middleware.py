from typing import Callable, Literal

import pytest

from aioscraper.exceptions import HTTPException, StopMiddlewareProcessing, StopRequestProcessing
from aioscraper.holders.middleware import MiddlewareType
from aioscraper.types import Request, Response, SendRequest, Middleware
from tests.mocks import MockAIOScraper, MockResponse


class MiddlewareScraper:
    def __init__(self) -> None:
        self.response = None
        self.outer: bool | None = None
        self.inner: bool | None = None
        self.response_flag: bool | None = None
        self.exception_seen = False

    async def __call__(self, send_request: SendRequest) -> None:
        await send_request(Request(url="https://api.test.com/v1", callback=self.parse))
        await send_request(Request(url="https://api.test.com/error", errback=self.handle_error))

    async def parse(self, response: Response, request: Request, outer: bool, inner: bool) -> None:
        self.response = response.json()
        self.outer = outer
        self.inner = inner
        self.response_flag = request.state.get("from_response")

    async def handle_error(self, exc: Exception) -> None:
        self.exception_seen = isinstance(exc, HTTPException)


def register_via_decorator(scraper: MockAIOScraper, middleware_type: MiddlewareType, fn: Middleware):
    scraper.middleware(middleware_type)(fn)


def register_via_add(scraper: MockAIOScraper, middleware_type: MiddlewareType, fn):
    scraper.middleware.add(middleware_type, fn)


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
    register: Callable[[MockAIOScraper, MiddlewareType, Middleware], None],
):
    mock_aioscraper.server.add("https://api.test.com/v1", handler=lambda _: {"status": "OK"})
    mock_aioscraper.server.add("https://api.test.com/error", handler=lambda _: MockResponse(status=500))

    calls = {"outer": 0, "inner": 0, "response": 0, "exception": 0}

    async def outer_middleware(request: Request) -> None:
        calls["outer"] += 1
        request.cb_kwargs["outer"] = True
        request.state["outer"] = True

    async def inner_middleware(request: Request) -> None:
        calls["inner"] += 1
        request.cb_kwargs["inner"] = True

    async def response_middleware(response: Response, request: Request) -> None:
        calls["response"] += 1
        request.state["from_response"] = True

    async def exception_middleware(exc: Exception) -> None:
        calls["exception"] += 1
        assert isinstance(exc, HTTPException)

    register(mock_aioscraper, "outer", outer_middleware)
    register(mock_aioscraper, "inner", inner_middleware)
    register(mock_aioscraper, "response", response_middleware)
    register(mock_aioscraper, "exception", exception_middleware)

    scraper = MiddlewareScraper()
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.start()

    assert scraper.response == {"status": "OK"}
    assert scraper.outer is True
    assert scraper.inner is True
    assert scraper.response_flag is True
    assert scraper.exception_seen is True
    assert calls == {"outer": 2, "inner": 2, "response": 2, "exception": 1}
    mock_aioscraper.server.assert_all_routes_handled()


@pytest.mark.asyncio
@pytest.mark.parametrize("middleware_type", ["inner", "response"])
async def test_stop_middleware_processing_short_circuits_chain(
    mock_aioscraper: MockAIOScraper,
    middleware_type: Literal["inner", "response"],
):
    mock_aioscraper.server.add("https://api.test.com/v1", handler=lambda _: {"status": "OK"})

    calls: list[str] = []

    async def first():
        calls.append("first")
        raise StopMiddlewareProcessing

    async def second():
        calls.append("second")

    mock_aioscraper.middleware.add(middleware_type, first, second)

    async def scrape(send_request: SendRequest) -> None:
        await send_request(Request(url="https://api.test.com/v1", callback=parse))

    async def parse() -> None:
        calls.append("callback")

    mock_aioscraper(scrape)

    async with mock_aioscraper:
        await mock_aioscraper.start()

    mock_aioscraper.server.assert_all_routes_handled()

    assert calls[0] == "first"
    assert "second" not in calls
    assert "exception" not in calls
    assert "callback" in calls


@pytest.mark.asyncio
@pytest.mark.parametrize("middleware_type", ["inner", "response"])
async def test_stop_request_processing_short_circuits_everything(
    mock_aioscraper: MockAIOScraper,
    middleware_type: Literal["inner", "response"],
):
    mock_aioscraper.server.add("https://api.test.com/v1", handler=lambda _: {"status": "OK"})

    calls: list[str] = []

    async def first():
        calls.append("first")
        raise StopRequestProcessing

    async def second():
        calls.append("second")

    mock_aioscraper.middleware.add(middleware_type, first, second)

    async def scrape(send_request: SendRequest) -> None:
        await send_request(Request(url="https://api.test.com/v1", callback=parse))

    async def parse() -> None:
        calls.append("callback")

    mock_aioscraper(scrape)

    async with mock_aioscraper:
        await mock_aioscraper.start()

    assert calls == ["first"]


@pytest.mark.asyncio
async def test_exception_middleware_stop_processing_skips_rest_and_errback(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/error", handler=lambda _: MockResponse(status=500))

    calls: list[str] = []

    async def exc_one():
        calls.append("exc1")
        raise StopMiddlewareProcessing

    async def exc_two():
        calls.append("exc2")

    async def errback():
        calls.append("errback")

    mock_aioscraper.middleware.add("exception", exc_one, exc_two)

    async def scrape(send_request: SendRequest) -> None:
        await send_request(Request(url="https://api.test.com/error", errback=errback))

    mock_aioscraper(scrape)

    async with mock_aioscraper:
        await mock_aioscraper.start()

    mock_aioscraper.server.assert_all_routes_handled()

    assert calls == ["exc1", "errback"]


@pytest.mark.asyncio
async def test_exception_middleware_stop_request_processing_skips_errback(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/error", handler=lambda _: MockResponse(status=500))

    calls: list[str] = []

    async def exc_one():
        calls.append("exc1")
        raise StopRequestProcessing

    async def exc_two():
        calls.append("exc2")

    async def errback():
        calls.append("errback")

    mock_aioscraper.middleware.add("exception", exc_one, exc_two)

    async def scrape(send_request: SendRequest) -> None:
        await send_request(Request(url="https://api.test.com/error", errback=errback))

    mock_aioscraper(scrape)

    async with mock_aioscraper:
        await mock_aioscraper.start()

    mock_aioscraper.server.assert_all_routes_handled()

    assert calls == ["exc1"]
