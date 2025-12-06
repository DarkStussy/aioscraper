import pytest

from aioscraper.types import Request, Response, SendRequest
from tests.mocks import MockAIOScraper


class Scraper:
    def __init__(self) -> None:
        self.seen: dict[str, str] | None = None

    async def __call__(self, send_request: SendRequest) -> None:
        await send_request(
            Request(
                url="https://api.test.com/params?static=1",
                method="GET",
                params={"q": "test", "page": 2},
                callback=self.parse,
            )
        )

    async def parse(self, response: Response, request: Request) -> None:
        self.seen = response.json()


@pytest.mark.asyncio
async def test_query_params_passed(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/params", handler=lambda r: dict(r.query))

    scraper = Scraper()
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.start()

    mock_aioscraper.server.assert_all_routes_handled()

    assert scraper.seen == {"static": "1", "q": "test", "page": "2"}
