import json

import pytest

from aioscraper.types import Request, Response, SendRequest
from tests.mocks import MockAIOScraper, MockResponse


class Scraper:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.parsed_ok = False

    async def __call__(self, send_request: SendRequest) -> None:
        await send_request(
            Request(
                url="https://api.test.com/bad-json",
                method="GET",
                callback=self.parse,
                errback=self.on_error,
            )
        )

    async def parse(self, response: Response) -> None:
        response.json()  # should raise JSONDecodeError on broken data
        self.parsed_ok = True

    async def on_error(self, exc: Exception) -> None:
        self.error = exc


@pytest.mark.asyncio
async def test_broken_json_triggers_errback(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/bad-json", handler=lambda _: MockResponse(text="not valid json"))

    scraper = Scraper()
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.start()

    mock_aioscraper.server.assert_all_routes_handled()

    assert isinstance(scraper.error, json.JSONDecodeError)
    assert scraper.parsed_ok is False
