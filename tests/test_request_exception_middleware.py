import pytest
from aresponses import ResponsesMockServer

from aioscraper import AIOScraper
from aioscraper.types import Response, RequestSender


class RequestExceptionMiddleware:
    def __init__(self) -> None:
        self.exc_handled = False

    async def __call__(self, exc: Exception) -> bool | None:
        self.exc_handled = True
        return True


class Scraper:
    def __init__(self) -> None:
        self.response_data = None
        self.exc_handled = False

    async def __call__(self, send_request: RequestSender) -> None:
        await send_request(url="https://api.test.com/v1", callback=self.parse, errback=self.error)

    async def parse(self, response: Response) -> None:
        raise Exception("Test Exception")

    async def error(self, exc: Exception) -> None:
        self.exc_handled = True


@pytest.mark.asyncio
async def test_request_exception_middleware(aresponses: ResponsesMockServer):
    aresponses.add("api.test.com", "/v1", "GET", response={"status": "OK"})  # type: ignore

    scraper = Scraper()
    middleware = RequestExceptionMiddleware()
    async with AIOScraper([scraper]) as s:
        s.add_request_exception_middlewares(middleware)
        await s.start()

    assert middleware.exc_handled is True
    assert scraper.exc_handled is False
    aresponses.assert_plan_strictly_followed()
