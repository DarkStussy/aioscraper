import pytest

from aioscraper.exceptions import HTTPException, StopMiddlewareProcessing
from aioscraper.types import Request, SendRequest, Response
from tests.mocks.scraper import MockAIOScraper
from tests.mocks.server import MockResponse


class RequestExceptionMiddleware:
    def __init__(self) -> None:
        self.exc_handled = False
        self.http_exc_handed = False

    async def __call__(self, exc: Exception) -> None:
        if isinstance(exc, HTTPException):
            self.http_exc_handed = True
        elif isinstance(exc, RuntimeError):
            self.exc_handled = True
        elif isinstance(exc, ValueError):
            return

        raise StopMiddlewareProcessing


class Scraper:
    def __init__(self) -> None:
        self.response_data = None
        self.exc_handled = False
        self.http_exc_handed = False

    async def __call__(self, send_request: SendRequest) -> None:
        await send_request(Request(url="https://api.test.com/v0", errback=self.http_error))
        await send_request(Request(url="https://api.test.com/v1", callback=self.parse, errback=self.error))
        await send_request(Request(url="https://api.test.com/v1", callback=self.parse_value, errback=self.error))

    async def parse(self, response: Response) -> None:
        raise RuntimeError("Test Exception")

    async def parse_value(self, response: Response) -> None:
        raise ValueError("Test Exception")

    async def http_error(self, exc: HTTPException) -> None:
        self.http_exc_handed = True

    async def error(self, exc: Exception) -> None:
        if isinstance(exc, RuntimeError):
            self.exc_handled = True


@pytest.mark.asyncio
async def test_request_exception_middleware(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/v0", handler=lambda _: MockResponse(status=404))
    mock_aioscraper.server.add("https://api.test.com/v1", handler=lambda _: {"status": "OK"}, repeat=2)

    scraper = Scraper()
    middleware = RequestExceptionMiddleware()
    mock_aioscraper(scraper)
    async with mock_aioscraper:
        mock_aioscraper.add_request_exception_middlewares(middleware)
        await mock_aioscraper.start()

    assert middleware.http_exc_handed is True
    assert scraper.http_exc_handed is False
    assert middleware.exc_handled is True
    assert scraper.exc_handled is False
    mock_aioscraper.server.assert_all_routes_handled()
