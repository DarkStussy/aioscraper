import pytest
from aresponses import ResponsesMockServer

from aioscraper import AIOScraper
from aioscraper.types import Request, SendRequest, Response


class Scraper:
    def __init__(self) -> None:
        self.results = {}

    async def __call__(self, send_request: SendRequest, dep: str) -> None:
        self.results["scraper_dep"] = dep
        await send_request(Request(url="https://api.test.com/deps", callback=self.parse))

    async def parse(self, response: Response, dep: str) -> None:
        self.results["response_dep"] = dep
        self.results["payload"] = response.json()


@pytest.mark.asyncio
async def test_dependencies(aresponses: ResponsesMockServer):
    response_data = {"status": "OK"}
    aresponses.add("api.test.com", "/deps", "GET", response=response_data)  # type: ignore

    scraper = Scraper()

    async with AIOScraper() as s:
        s.register(scraper)
        s.register_dependencies(dep="injected")
        await s.start()

    assert scraper.results["scraper_dep"] == "injected"
    assert scraper.results["response_dep"] == "injected"
    assert scraper.results["payload"] == response_data
    aresponses.assert_plan_strictly_followed()
