import pytest

from aioscraper.types import Request, SendRequest, Response
from tests.mocks.scraper import MockAIOScraper


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
async def test_dependencies(mock_aioscraper: MockAIOScraper):
    response_data = {"status": "OK"}
    mock_aioscraper.server.add("https://api.test.com/deps", handler=lambda _: response_data)

    scraper = Scraper()

    mock_aioscraper.register(scraper)
    async with mock_aioscraper:
        mock_aioscraper.register_dependencies(dep="injected")
        await mock_aioscraper.start()

    assert scraper.results["scraper_dep"] == "injected"
    assert scraper.results["response_dep"] == "injected"
    assert scraper.results["payload"] == response_data
    mock_aioscraper.server.assert_all_routes_handled()
