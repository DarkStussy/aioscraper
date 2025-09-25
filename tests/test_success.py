import pytest
from aresponses import ResponsesMockServer

from aioscraper import AIOScraper
from aioscraper.types import RequestSender, Response


class Scraper:
    def __init__(self) -> None:
        self.response_data = None

    async def __call__(self, send_request: RequestSender) -> None:
        await send_request(url="https://api.test.com/v1", callback=self.parse)

    async def parse(self, response: Response) -> None:
        self.response_data = response.json()


@pytest.mark.asyncio
async def test_success(aresponses: ResponsesMockServer):
    response_data = {"status": "OK"}
    aresponses.add("api.test.com", "/v1", "GET", response=response_data)  # type: ignore

    scraper = Scraper()
    async with AIOScraper([scraper]) as s:
        await s.start()

    assert scraper.response_data == response_data
    aresponses.assert_plan_strictly_followed()
