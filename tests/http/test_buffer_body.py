from dataclasses import replace

import pytest
from aiohttp import web

from aioscraper.config import AdaptiveRateLimitConfig, Config, RateLimitConfig, RequestRetryConfig, SessionConfig
from aioscraper.core.rate_limiter import RateLimitManager, RequestOutcome
from aioscraper.exceptions import ConnectionFailed
from aioscraper.types import Request, Response, ScheduleRequest
from tests.mocks import MockAIOScraper

_URL = "https://api.test.com/flaky-body"
_BODY = b"x" * 4096


def _truncate_until(succeed_from: int):
    """Serve a body that stops early until the given attempt, then the whole thing."""
    attempts = 0

    async def handler(request: web.BaseRequest) -> web.StreamResponse:
        nonlocal attempts
        attempts += 1
        response = web.StreamResponse(status=200, headers={"Content-Length": str(len(_BODY))})
        await response.prepare(request)

        if attempts >= succeed_from:
            await response.write(_BODY)
            return response

        await response.write(_BODY[:16])
        request.transport.close()  # type: ignore[reportOptionalMemberAccess]
        return response

    return handler, lambda: attempts


class _Scraper:
    def __init__(self, **request_kwargs: object):
        self._request_kwargs = request_kwargs
        self.body: bytes | None = None
        self.error: Exception | None = None

    async def __call__(self, schedule_request: ScheduleRequest):
        await schedule_request(
            Request(_URL, callback=self.parse, errback=self.on_error, **self._request_kwargs),  # type: ignore[reportArgumentType]
        )

    async def parse(self, response: Response):
        self.body = await response.read()

    async def on_error(self, exc: Exception):
        self.error = exc


def _configure(scraper: MockAIOScraper, **session_kwargs: object):
    "The default cap must not be what fails the read, and retries are what the buffering feeds."
    session = replace(
        SessionConfig(retry=RequestRetryConfig(attempts=3, base_delay=0.01), max_response_body_size=None),
        **session_kwargs,  # type: ignore[reportArgumentType]
    )
    scraper.config = Config(session=session)


@pytest.mark.asyncio
async def test_a_truncated_body_is_retried_when_buffered(mock_aioscraper: MockAIOScraper):
    handler, attempts = _truncate_until(succeed_from=2)
    mock_aioscraper.server.add(_URL, handler=handler, repeat=2)
    scraper = _Scraper(buffer_body=True)
    mock_aioscraper(scraper)
    _configure(mock_aioscraper)

    async with mock_aioscraper:
        result = await mock_aioscraper.wait()

    assert scraper.error is None
    assert scraper.body == _BODY
    assert attempts() == 2
    assert result.requests_retried == 1


@pytest.mark.asyncio
async def test_a_truncated_body_is_not_retried_without_buffering(mock_aioscraper: MockAIOScraper):
    """The read happens in the callback, past the retry policy, so the errback is the only outcome."""
    handler, attempts = _truncate_until(succeed_from=2)
    mock_aioscraper.server.add(_URL, handler=handler, repeat=2)
    scraper = _Scraper()
    mock_aioscraper(scraper)
    _configure(mock_aioscraper)

    async with mock_aioscraper:
        result = await mock_aioscraper.wait()

    assert isinstance(scraper.error, ConnectionFailed)
    assert scraper.body is None
    assert attempts() == 1
    assert result.requests_retried == 0


@pytest.mark.asyncio
async def test_the_session_default_applies_and_the_request_overrides_it(mock_aioscraper: MockAIOScraper):
    handler, attempts = _truncate_until(succeed_from=2)
    mock_aioscraper.server.add(_URL, handler=handler, repeat=2)
    scraper = _Scraper(buffer_body=False)
    mock_aioscraper(scraper)
    _configure(mock_aioscraper, buffer_body=True)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert isinstance(scraper.error, ConnectionFailed)
    assert attempts() == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(("buffer_body", "expected"), [(True, ConnectionFailed), (False, None)])
async def test_a_buffered_body_failure_reaches_the_rate_limiter(
    mock_aioscraper: MockAIOScraper,
    monkeypatch: pytest.MonkeyPatch,
    buffer_body: bool,
    expected: type[Exception] | None,
):
    """Unbuffered, the outcome is recorded when the headers arrive, so the body never counts."""
    outcomes: list[RequestOutcome] = []
    record = RateLimitManager.on_request_outcome

    def capture(self: RateLimitManager, outcome: RequestOutcome):
        outcomes.append(outcome)
        record(self, outcome)

    monkeypatch.setattr(RateLimitManager, "on_request_outcome", capture)

    handler, _ = _truncate_until(succeed_from=2)
    mock_aioscraper.server.add(_URL, handler=handler, repeat=1)
    scraper = _Scraper(buffer_body=buffer_body)
    mock_aioscraper(scraper)
    _configure(
        mock_aioscraper,
        retry=RequestRetryConfig(enabled=False),
        rate_limit=RateLimitConfig(per_group=True, adaptive=AdaptiveRateLimitConfig()),
    )

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert isinstance(scraper.error, ConnectionFailed)
    assert [outcome.exception_type for outcome in outcomes] == [expected]


@pytest.mark.asyncio
async def test_a_buffered_body_replays_to_the_stream(mock_aioscraper: MockAIOScraper):
    chunks: list[bytes] = []

    async def parse(response: Response):
        chunks.extend([chunk async for chunk in response.iter_bytes(chunk_size=1024)])

    async def scraper(schedule_request: ScheduleRequest):
        await schedule_request(Request(_URL, callback=parse, buffer_body=True))

    mock_aioscraper.server.add(_URL, handler=lambda _: web.Response(body=_BODY))
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert b"".join(chunks) == _BODY
    assert len(chunks) == 4
