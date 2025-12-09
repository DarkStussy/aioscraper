import pytest

from aioscraper.types import Request, Response, SendRequest
from tests.mocks import MockAIOScraper, MockResponse


class Scraper:
    def __init__(self, allow_redirects: bool):
        self.allow_redirects = allow_redirects
        self.final_url: str | None = None
        self.status: int | None = None

    async def __call__(self, send_request: SendRequest):
        await send_request(
            Request(
                url="https://api.test.com/redirect",
                method="GET",
                allow_redirects=self.allow_redirects,
                callback=self.parse,
            )
        )

    async def parse(self, response: Response):
        self.final_url = response.url
        self.status = response.status


@pytest.mark.asyncio
async def test_redirect_followed(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add(
        "https://api.test.com/redirect",
        handler=lambda _: MockResponse(status=302, headers={"Location": "https://api.test.com/final"}),
    )
    mock_aioscraper.server.add("https://api.test.com/final", handler=lambda _: MockResponse(text="done"))

    scraper = Scraper(allow_redirects=True)
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    mock_aioscraper.server.assert_all_routes_handled()

    assert scraper.status == 200
    assert scraper.final_url == "https://api.test.com/final"


@pytest.mark.asyncio
async def test_redirect_not_followed(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add(
        "https://api.test.com/redirect",
        handler=lambda _: MockResponse(status=302, headers={"Location": "https://api.test.com/final"}),
    )

    scraper = Scraper(allow_redirects=False)
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    mock_aioscraper.server.assert_no_unused_routes(ignore_infinite_repeats=True)

    assert scraper.status == 302
    assert scraper.final_url == "https://api.test.com/redirect"
