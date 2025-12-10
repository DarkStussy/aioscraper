from typing import Any

import pytest

from aioscraper.types import Request, Response, SendRequest
from tests.mocks import MockAIOScraper, MockResponse


class Scraper:
    def __init__(self):
        self.seen_cookies: dict[str, str] | None = None
        self.response_cookies: dict[str, Any] | None = None

    async def __call__(self, send_request: SendRequest):
        await send_request(
            Request(
                url="https://api.test.com/cookies",
                method="GET",
                cookies={"session": "abc123"},
                callback=self.parse,
            ),
        )

    async def parse(self, response: Response, request: Request):
        self.seen_cookies = await response.json()
        self.response_cookies = response.cookies


@pytest.mark.asyncio
async def test_cookies_passed_to_server(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add(
        "https://api.test.com/cookies",
        handler=lambda r: {"session": r.cookies.get("session")},
    )

    scraper = Scraper()
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    mock_aioscraper.server.assert_all_routes_handled()

    assert scraper.seen_cookies == {"session": "abc123"}


@pytest.mark.asyncio
async def test_cookies_received_from_server(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add(
        "https://api.test.com/cookies",
        handler=lambda _: MockResponse(json={"ok": True}, headers={"Set-Cookie": "token=xyz; Path=/"}),
    )

    scraper = Scraper()
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    mock_aioscraper.server.assert_all_routes_handled()

    assert scraper.response_cookies is not None
    assert scraper.response_cookies["token"].value == "xyz"
