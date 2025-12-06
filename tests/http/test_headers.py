from typing import Mapping
import pytest

from aioscraper.types import Request, Response, SendRequest
from tests.mocks import MockAIOScraper, MockResponse


class Scraper:
    def __init__(self) -> None:
        self.seen_headers: dict[str, str] | None = None
        self.response_headers: Mapping[str, str] | None = None

    async def __call__(self, send_request: SendRequest) -> None:
        await send_request(
            Request(
                url="https://api.test.com/headers",
                method="GET",
                headers={"X-Test": "header"},
                callback=self.parse,
            )
        )

    async def parse(self, response: Response, request: Request) -> None:
        self.seen_headers = response.json()
        self.response_headers = response.headers


@pytest.mark.asyncio
async def test_headers_passed_to_server(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/headers", handler=lambda r: {"X-Test": r.headers.get("X-Test")})

    scraper = Scraper()
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.start()

    mock_aioscraper.server.assert_all_routes_handled()

    assert scraper.seen_headers is not None
    assert scraper.seen_headers["X-Test"] == "header"


@pytest.mark.asyncio
async def test_response_headers_received(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add(
        "https://api.test.com/headers",
        handler=lambda _: MockResponse(json={"ok": True}, headers={"X-From-Server": "ok"}),
    )

    scraper = Scraper()
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.start()

    mock_aioscraper.server.assert_all_routes_handled()

    assert scraper.response_headers is not None
    assert scraper.response_headers["X-From-Server"] == "ok"
