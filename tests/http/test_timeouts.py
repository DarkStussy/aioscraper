import asyncio

from httpx import ReadTimeout, TimeoutException
import pytest

from aioscraper.types import Request, Response, SendRequest
from aioscraper.config import Config, SessionConfig
from tests.mocks import MockAIOScraper, MockResponse


class Scraper:
    def __init__(self, timeout: float | None):
        self.timeout = timeout
        self.result: str | None = None
        self.error: Exception | None = None

    async def __call__(self, send_request: SendRequest):
        await send_request(
            Request(
                url="https://api.test.com/slow",
                method="GET",
                timeout=self.timeout,
                callback=self.parse,
                errback=self.on_error,
            )
        )

    async def parse(self, response: Response):
        self.result = response.text()

    async def on_error(self, exc: Exception):
        self.error = exc


@pytest.mark.asyncio
async def test_request_timeout_triggers_errback(mock_aioscraper: MockAIOScraper):
    async def slow_handler(_):
        await asyncio.sleep(0.05)
        return MockResponse(text="ok")

    mock_aioscraper.server.add("https://api.test.com/slow", handler=slow_handler)

    scraper = Scraper(timeout=0.01)
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.start()

    assert isinstance(scraper.error, (ReadTimeout, asyncio.TimeoutError))
    assert scraper.result is None


@pytest.mark.asyncio
async def test_no_timeout_succeeds(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/slow", handler=lambda _: MockResponse(text="ok"))

    scraper = Scraper(timeout=1.0)
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.start()

    assert scraper.result == "ok"
    assert scraper.error is None


@pytest.mark.asyncio
async def test_global_timeout_from_config(mock_aioscraper: MockAIOScraper):
    async def slow_handler(_):
        await asyncio.sleep(0.05)
        return MockResponse(text="ok")

    mock_aioscraper.server.add("https://api.test.com/slow", handler=slow_handler)

    scraper = Scraper(timeout=None)
    mock_aioscraper(scraper)

    config = Config(session=SessionConfig(timeout=0.01))

    async with mock_aioscraper:
        await mock_aioscraper.start(config)

    assert scraper.result is None
    assert isinstance(scraper.error, (TimeoutException, asyncio.TimeoutError))
