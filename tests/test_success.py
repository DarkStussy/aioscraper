import pytest

from aioscraper.types import Request, SendRequest, Response
from tests.mocks import MockAIOScraper


class Scraper:
    def __init__(self) -> None:
        self.response_data = None

    async def __call__(self, send_request: SendRequest) -> None:
        await send_request(Request(url="http://api.test.com/v1", callback=self.parse))

    async def parse(self, response: Response) -> None:
        self.response_data = response.json()


@pytest.mark.asyncio
async def test_success(mock_aioscraper: MockAIOScraper):
    response_data = {"status": "OK"}
    mock_aioscraper.server.add("https://api.test.com/v1", handler=lambda _: response_data)

    scraper = Scraper()
    mock_aioscraper.register(scraper)
    async with mock_aioscraper:
        await mock_aioscraper.start()

    assert scraper.response_data == response_data
    mock_aioscraper.server.assert_all_routes_handled()
