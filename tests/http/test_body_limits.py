import pytest
from aiohttp import web

from aioscraper.config import Config, SessionConfig
from aioscraper.exceptions import HTTPException, ResponseTooLarge
from aioscraper.types import Request, Response, SendRequest
from tests.mocks import MockAIOScraper, MockResponse

BODY_SIZE = 256 * 1024


class BodyScraper:
    """Reads whole bodies and records what came back."""

    def __init__(self, *urls: str):
        self.urls = urls
        self.bodies: list[bytes] = []
        self.errors: list[Exception] = []

    async def __call__(self, send_request: SendRequest):
        for url in self.urls:
            await send_request(Request(url=url, callback=self.parse, errback=self.on_error))

    async def parse(self, response: Response):
        self.bodies.append(await response.read())

    async def on_error(self, exc: Exception):
        self.errors.append(exc)


class StreamingScraper:
    """Reads one chunk of the first response, then requests a second URL."""

    def __init__(self, stream_url: str, follow_up_url: str, chunk_size: int):
        self._stream_url = stream_url
        self._follow_up_url = follow_up_url
        self._chunk_size = chunk_size
        self.first_chunk: bytes | None = None
        self.follow_up: bytes | None = None
        self.errors: list[Exception] = []

    async def __call__(self, send_request: SendRequest):
        await send_request(Request(url=self._stream_url, callback=self.stream, errback=self.on_error))

    async def stream(self, response: Response, send_request: SendRequest):
        async for chunk in response.iter_bytes(self._chunk_size):
            self.first_chunk = chunk
            break

        await send_request(Request(url=self._follow_up_url, callback=self.parse_follow_up, errback=self.on_error))

    async def parse_follow_up(self, response: Response):
        self.follow_up = await response.read()

    async def on_error(self, exc: Exception):
        self.errors.append(exc)


def _configure(scraper: MockAIOScraper, **session_kwargs):
    scraper.config = Config(session=SessionConfig(**session_kwargs))


@pytest.mark.asyncio
async def test_body_over_the_limit_is_rejected(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/large", handler=lambda _: MockResponse(text="x" * BODY_SIZE))

    scraper = BodyScraper("https://api.test.com/large")
    mock_aioscraper(scraper)
    _configure(mock_aioscraper, max_response_body_size=1024)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert not scraper.bodies
    assert len(scraper.errors) == 1
    assert isinstance(scraper.errors[0], ResponseTooLarge)
    assert scraper.errors[0].limit == 1024


@pytest.mark.asyncio
async def test_body_under_the_limit_is_read(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/small", handler=lambda _: MockResponse(text="x" * 512))

    scraper = BodyScraper("https://api.test.com/small")
    mock_aioscraper(scraper)
    _configure(mock_aioscraper, max_response_body_size=1024)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert not scraper.errors
    assert scraper.bodies == [b"x" * 512]


@pytest.mark.asyncio
async def test_unlimited_by_default(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/large", handler=lambda _: MockResponse(text="x" * BODY_SIZE))

    scraper = BodyScraper("https://api.test.com/large")
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert not scraper.errors
    assert scraper.bodies == [b"x" * BODY_SIZE]


@pytest.mark.asyncio
async def test_error_body_is_truncated(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add(
        "https://api.test.com/boom",
        handler=lambda _: MockResponse(status=500, text="x" * BODY_SIZE),
    )

    scraper = BodyScraper("https://api.test.com/boom")
    mock_aioscraper(scraper)
    _configure(mock_aioscraper, max_error_body_size=128)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert len(scraper.errors) == 1
    error = scraper.errors[0]
    assert isinstance(error, HTTPException)
    assert error.message == "x" * 128 + " [truncated]"


@pytest.mark.asyncio
async def test_short_error_body_is_kept_whole(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add(
        "https://api.test.com/boom",
        handler=lambda _: MockResponse(status=500, text="boom"),
    )

    scraper = BodyScraper("https://api.test.com/boom")
    mock_aioscraper(scraper)
    _configure(mock_aioscraper, max_error_body_size=128)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert len(scraper.errors) == 1
    error = scraper.errors[0]
    assert isinstance(error, HTTPException)
    assert error.message == "boom"


@pytest.mark.asyncio
async def test_error_body_can_be_disabled(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add(
        "https://api.test.com/boom",
        handler=lambda _: MockResponse(status=500, text="boom"),
    )

    scraper = BodyScraper("https://api.test.com/boom")
    mock_aioscraper(scraper)
    _configure(mock_aioscraper, max_error_body_size=0)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert len(scraper.errors) == 1
    error = scraper.errors[0]
    assert isinstance(error, HTTPException)
    assert error.message == ""


@pytest.mark.asyncio
async def test_error_body_ignores_the_response_limit(mock_aioscraper: MockAIOScraper):
    """A body too large to hand to a callback must still produce an HTTPException."""
    mock_aioscraper.server.add(
        "https://api.test.com/boom",
        handler=lambda _: MockResponse(status=500, text="x" * BODY_SIZE),
    )

    scraper = BodyScraper("https://api.test.com/boom")
    mock_aioscraper(scraper)
    _configure(mock_aioscraper, max_response_body_size=1024, max_error_body_size=64)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert len(scraper.errors) == 1
    error = scraper.errors[0]
    assert isinstance(error, HTTPException)
    assert error.status_code == 500
    assert error.message == "x" * 64 + " [truncated]"


@pytest.mark.asyncio
async def test_early_break_releases_the_connection(mock_aioscraper: MockAIOScraper):
    """Abandoning a stream must not wedge the connection pool for later requests."""

    async def slow_stream(request: web.BaseRequest) -> web.StreamResponse:
        response = web.StreamResponse(status=200, headers={"Content-Type": "application/octet-stream"})
        await response.prepare(request)
        for _ in range(64):
            await response.write(b"x" * 8192)

        await response.write_eof()
        return response

    mock_aioscraper.server.add("https://api.test.com/stream", handler=slow_stream)
    mock_aioscraper.server.add("https://api.test.com/after", handler=lambda _: MockResponse(text="after"))

    scraper = StreamingScraper("https://api.test.com/stream", "https://api.test.com/after", chunk_size=8192)
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    mock_aioscraper.server.assert_all_routes_handled()

    assert not scraper.errors
    assert scraper.first_chunk is not None
    assert len(scraper.first_chunk) <= 8192
    assert scraper.follow_up == b"after"
