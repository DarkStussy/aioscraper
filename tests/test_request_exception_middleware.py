import pytest
from aresponses import ResponsesMockServer

from aioscraper import AIOScraper
from aioscraper.exceptions import HTTPException, StopMiddlewareProcessing
from aioscraper.types import Request, SendRequest, Response


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
async def test_request_exception_middleware(aresponses: ResponsesMockServer):
    def handle_request(request):
        return aresponses.Response(status=404)

    aresponses.add("api.test.com", "/v0", "GET", response=handle_request)  # type: ignore
    aresponses.add("api.test.com", "/v1", "GET", response={"status": "OK"}, repeat=2)  # type: ignore

    scraper = Scraper()
    middleware = RequestExceptionMiddleware()
    async with AIOScraper(scraper) as s:
        s.add_request_exception_middlewares(middleware)
        await s.start()

    assert middleware.http_exc_handed is True
    assert scraper.http_exc_handed is False
    assert middleware.exc_handled is True
    assert scraper.exc_handled is False
    aresponses.assert_plan_strictly_followed()
