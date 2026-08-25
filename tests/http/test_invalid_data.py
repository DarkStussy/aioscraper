import json

import pytest

from aioscraper.exceptions import InvalidURL
from aioscraper.types import Request, Response, ScheduleRequest
from tests.mocks import MockAIOScraper, MockResponse


class Scraper:
    def __init__(self):
        self.error: Exception | None = None
        self.parsed_ok = False

    async def __call__(self, schedule_request: ScheduleRequest):
        await schedule_request(
            Request(
                url="https://api.test.com/bad-json",
                method="GET",
                callback=self.parse,
                errback=self.on_error,
            ),
        )

    async def parse(self, response: Response):
        await response.json()  # should raise JSONDecodeError on broken data
        self.parsed_ok = True

    async def on_error(self, exc: Exception):
        self.error = exc


@pytest.mark.asyncio
async def test_broken_json_triggers_errback(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/bad-json", handler=lambda _: MockResponse(text="not valid json"))

    scraper = Scraper()
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    mock_aioscraper.server.assert_all_routes_handled()

    assert isinstance(scraper.error, json.JSONDecodeError)
    assert scraper.parsed_ok is False


class _BadUrlScraper:
    """Sends a URL no parser accepts, first as it is and then through a middleware."""

    def __init__(self, url: str, *, via_middleware: bool):
        self._url = url
        self._via_middleware = via_middleware
        self.sent_error: Exception | None = None
        self.error: Exception | None = None

    async def __call__(self, schedule_request: ScheduleRequest):
        url = "https://api.test.com/ok" if self._via_middleware else self._url
        try:
            await schedule_request(Request(url=url, errback=self.on_error))
        except Exception as exc:
            self.sent_error = exc

    async def on_error(self, exc: Exception):
        self.error = exc


@pytest.mark.asyncio
async def test_an_unparsable_url_is_rejected_when_sent(mock_aioscraper: MockAIOScraper):
    scraper = _BadUrlScraper("http://[::1", via_middleware=False)
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        result = await mock_aioscraper.wait()

    assert isinstance(scraper.sent_error, InvalidURL)
    assert result.requests_started == 0


@pytest.mark.asyncio
async def test_an_unparsable_url_from_a_middleware_reaches_the_errback(mock_aioscraper: MockAIOScraper):
    """Nothing may raise it past the dispatcher, where no errback and no counter would see it."""

    @mock_aioscraper.middleware
    def factory():
        async def middleware(call_next, request: Request):
            request.url = "http://[::1"
            return await call_next(request)

        return middleware

    scraper = _BadUrlScraper("http://[::1", via_middleware=True)
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        result = await mock_aioscraper.wait()

    assert scraper.sent_error is None
    assert isinstance(scraper.error, InvalidURL)
    assert result.requests_started == 1
    assert result.requests_failed == 1
