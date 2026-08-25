import pytest
from aiohttp import web

from aioscraper.types import Request, Response, ScheduleRequest
from aioscraper.types.session import ResponseHeaders
from tests.mocks import MockAIOScraper, MockResponse


class Scraper:
    def __init__(self):
        self.seen_headers: dict[str, str] | None = None
        self.response_headers: ResponseHeaders | None = None

    async def __call__(self, schedule_request: ScheduleRequest):
        await schedule_request(
            Request(
                url="https://api.test.com/headers",
                method="GET",
                headers={"X-Test": "header"},
                callback=self.parse,
            ),
        )

    async def parse(self, response: Response, request: Request):
        self.seen_headers = await response.json()
        self.response_headers = response.headers


@pytest.mark.asyncio
async def test_headers_passed_to_server(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/headers", handler=lambda r: {"X-Test": r.headers.get("X-Test")})

    scraper = Scraper()
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

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
        await mock_aioscraper.wait()

    mock_aioscraper.server.assert_all_routes_handled()

    assert scraper.response_headers is not None
    assert scraper.response_headers["X-From-Server"] == "ok"
    # header names are case-insensitive, and httpx lowercases the ones it parses
    assert scraper.response_headers["x-from-server"] == "ok"


@pytest.mark.asyncio
async def test_a_repeated_header_keeps_every_value(mock_aioscraper: MockAIOScraper):
    """httpx joins repeated headers on lookup and aiohttp returns the first; both must not."""

    def two_cookies(request: web.BaseRequest) -> web.StreamResponse:
        response = web.json_response(data={"ok": True})
        response.headers.add("Set-Cookie", "a=1")
        response.headers.add("Set-Cookie", "b=2")
        return response

    mock_aioscraper.server.add("https://api.test.com/headers", handler=two_cookies)

    scraper = Scraper()
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert scraper.response_headers is not None
    assert scraper.response_headers.getall("Set-Cookie") == ["a=1", "b=2"]
    assert scraper.response_headers["Set-Cookie"] == "a=1"
