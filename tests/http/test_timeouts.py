import asyncio

import pytest
from aiohttp import web

from aioscraper.config import Config, SessionConfig
from aioscraper.exceptions import InvalidRequestData, TransportTimeout
from aioscraper.types import Request, Response, SendRequest
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
            ),
        )

    async def parse(self, response: Response):
        self.result = await response.text()

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
        await mock_aioscraper.wait()

    assert isinstance(scraper.error, TransportTimeout)
    assert scraper.result is None


@pytest.mark.asyncio
async def test_no_timeout_succeeds(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/slow", handler=lambda _: MockResponse(text="ok"))

    scraper = Scraper(timeout=1.0)
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

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

    mock_aioscraper.config = Config(session=SessionConfig(timeout=0.01))

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert scraper.result is None
    assert isinstance(scraper.error, TransportTimeout)
    # the class aiohttp raises on its own, which a policy written for it still catches
    assert isinstance(scraper.error, asyncio.TimeoutError)


class _StreamScraper:
    def __init__(self, url: str, timeout: float | None):
        self._url = url
        self._timeout = timeout
        self.error: Exception | None = None
        self.body: bytes | None = None

    async def __call__(self, send_request: SendRequest):
        await send_request(
            Request(url=self._url, timeout=self._timeout, callback=self.parse, errback=self.on_error),
        )

    async def parse(self, response: Response):
        self.body = await response.read()

    async def on_error(self, exc: Exception):
        self.error = exc


def _drip(chunks: int, pause: float):
    "A body that arrives one chunk at a time, each within any per-phase read timeout."

    async def handler(request: web.BaseRequest) -> web.StreamResponse:
        response = web.StreamResponse(status=200)
        await response.prepare(request)
        for _ in range(chunks):
            await response.write(b"x" * 8)
            await asyncio.sleep(pause)

        await response.write_eof()
        return response

    return handler


@pytest.mark.asyncio
async def test_the_timeout_is_a_budget_for_the_whole_response(mock_aioscraper: MockAIOScraper):
    """A drip-fed body must not outlive the timeout on any backend: httpx times each phase, not the
    request, so the framework holds the budget itself."""
    mock_aioscraper.server.add("https://api.test.com/drip", handler=_drip(chunks=40, pause=0.05))

    scraper = _StreamScraper("https://api.test.com/drip", timeout=0.3)
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert scraper.body is None
    assert isinstance(scraper.error, TransportTimeout)


@pytest.mark.asyncio
async def test_a_body_within_the_budget_is_read_whole(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/drip", handler=_drip(chunks=4, pause=0.01))

    scraper = _StreamScraper("https://api.test.com/drip", timeout=5.0)
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert scraper.error is None
    assert scraper.body == b"x" * 32


@pytest.mark.parametrize("timeout", [0, -1.0, float("nan"), float("inf")])
@pytest.mark.asyncio
async def test_a_non_positive_timeout_is_rejected(mock_aioscraper: MockAIOScraper, timeout: float):
    """Every backend gets the same answer, instead of aiohttp and httpx each inventing one."""
    sent: list[Request] = []

    @mock_aioscraper
    async def scraper(send_request: SendRequest):
        with pytest.raises(InvalidRequestData, match="positive"):
            await send_request(Request(url="https://api.test.com/slow", timeout=timeout))

        sent.append(await send_request(Request(url="https://api.test.com/slow", timeout=1.0)))

    mock_aioscraper.server.add("https://api.test.com/slow", handler=lambda _: MockResponse(text="ok"))

    async with mock_aioscraper:
        result = await mock_aioscraper.wait()

    assert len(sent) == 1
    assert result.ok is True
