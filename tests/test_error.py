import pytest

from aioscraper.exceptions import ClientException, HTTPException
from aioscraper.types import Request, Response, SendRequest
from tests.mocks import MockAIOScraper, MockResponse


class Scraper:
    def __init__(self):
        self.status = None
        self.response_data = None

    async def __call__(self, send_request: SendRequest):
        await send_request(Request(url="https://api.test.com/v1", errback=self.errback))

    async def errback(self, exc: ClientException):
        if isinstance(exc, HTTPException):
            self.status = exc.status_code
            self.response_data = exc.message


@pytest.mark.asyncio
async def test_error(mock_aioscraper: MockAIOScraper):
    response_data = "Internal Server Error"
    mock_aioscraper.server.add(
        "https://api.test.com/v1",
        handler=lambda _: MockResponse(status=500, text=response_data),
    )

    scraper = Scraper()
    mock_aioscraper(scraper)
    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert scraper.status == 500
    assert scraper.response_data == response_data
    mock_aioscraper.server.assert_all_routes_handled()


class CallbackErrorScraper:
    def __init__(self):
        self.exc_message = None
        self.request_url = None

    async def __call__(self, send_request: SendRequest):
        await send_request(Request(url="https://api.test.com/v2", callback=self.parse, errback=self.errback))

    async def parse(self, response: Response):
        raise RuntimeError("parse failed")

    async def errback(self, exc: Exception, request: Request):
        self.exc_message = str(exc)
        self.request_url = request.url


@pytest.mark.asyncio
async def test_callback_error_triggers_errback(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/v2")

    scraper = CallbackErrorScraper()
    mock_aioscraper(scraper)
    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert scraper.exc_message == "parse failed"
    assert scraper.request_url == "https://api.test.com/v2"
    mock_aioscraper.server.assert_all_routes_handled()


class ErrbackKwargsScraper:
    def __init__(self):
        self.status = None
        self.meta = None

    async def __call__(self, send_request: SendRequest):
        await send_request(Request(url="https://api.test.com/v3", errback=self.errback, cb_kwargs={"meta": "value"}))

    async def errback(self, exc: ClientException, meta: str):
        if isinstance(exc, HTTPException):
            self.status = exc.status_code
        self.meta = meta


@pytest.mark.asyncio
async def test_errback_receives_cb_kwargs(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add(
        "https://api.test.com/v3",
        handler=lambda _: MockResponse(status=503, text="Service Unavailable"),
    )

    scraper = ErrbackKwargsScraper()
    mock_aioscraper(scraper)
    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert scraper.status == 503
    assert scraper.meta == "value"
    mock_aioscraper.server.assert_all_routes_handled()
