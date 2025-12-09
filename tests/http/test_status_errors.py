import pytest

from aioscraper.exceptions import HTTPException
from aioscraper.types import Request, Response, SendRequest
from tests.mocks import MockAIOScraper, MockResponse


class Scraper:
    def __init__(self, status: int):
        self.status = status
        self.seen_error: HTTPException | None = None
        self.seen_response: Response | None = None

    async def __call__(self, send_request: SendRequest):
        await send_request(
            Request(
                url=f"https://api.test.com/{self.status}",
                method="GET",
                callback=self.parse,
                errback=self.on_error,
            )
        )

    async def parse(self, response: Response):
        self.seen_response = response

    async def on_error(self, exc: Exception):
        if isinstance(exc, HTTPException):
            self.seen_error = exc


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [400, 404, 500])
async def test_status_errors_raise_http_exception(mock_aioscraper: MockAIOScraper, status: int):
    mock_aioscraper.server.add(f"https://api.test.com/{status}", handler=lambda _: MockResponse(status=status))

    scraper = Scraper(status)
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert scraper.seen_response is None
    assert isinstance(scraper.seen_error, HTTPException)
    assert scraper.seen_error.status_code == status
    assert scraper.seen_error.url == f"https://api.test.com/{status}"


@pytest.mark.asyncio
async def test_status_ok_calls_callback(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/200", handler=lambda _: {"ok": True})

    scraper = Scraper(200)
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert scraper.seen_error is None
    assert scraper.seen_response is not None
    assert scraper.seen_response.status == 200
