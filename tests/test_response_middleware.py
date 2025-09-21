import pytest
from aresponses import ResponsesMockServer

from aioscraper import AIOScraper, BaseScraper
from aioscraper.types import Response, RequestSender


class ResponseMiddleware:
    def __init__(self) -> None:
        self.response_data = None

    async def __call__(self, response: Response) -> None:
        self.response_data = response.json()


class Scraper(BaseScraper):
    def __init__(self) -> None:
        self.response_data = None

    async def start(self, send_request: RequestSender) -> None:
        await send_request(url="https://api.test.com/v1", callback=self.parse)

    async def parse(self, response: Response) -> None:
        self.response_data = response.json()


@pytest.mark.asyncio
async def test_response_middleware(aresponses: ResponsesMockServer):
    response_data = {"status": "OK"}
    aresponses.add("api.test.com", "/v1", "GET", response=response_data)  # type: ignore

    middleware = ResponseMiddleware()
    scraper = Scraper()
    async with AIOScraper([scraper]) as executor:
        executor.add_response_middlewares(middleware)
        await executor.start()

    assert scraper.response_data == response_data
    assert middleware.response_data == response_data
    aresponses.assert_plan_strictly_followed()
