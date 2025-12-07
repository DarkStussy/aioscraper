import asyncio

import pytest

from aioscraper.config import Config, SessionConfig, RequestRetryConfig
from aioscraper.exceptions import HTTPException, StopRequestProcessing
from aioscraper.middlewares.retry import RETRY_STATE_KEY, RetryMiddleware
from aioscraper.types import Request, Response, SendRequest
from tests.mocks import MockAIOScraper, MockResponse


async def _noop_send(req: Request):
    return req


@pytest.mark.asyncio
async def test_retry_middleware_retries_on_status():
    middleware = RetryMiddleware(RequestRetryConfig(enabled=True, attempts=2, statuses=(502,), exceptions=()))
    request = Request(url="https://example.com")
    send_calls = 0

    async def send(req: Request):
        nonlocal send_calls
        send_calls += 1
        return req

    exc = HTTPException(
        url="https://example.com",
        method="GET",
        status_code=502,
        headers={},
        message="bad gateway",
    )

    with pytest.raises(StopRequestProcessing):
        await middleware(request=request, exc=exc, send_request=send)

    assert send_calls == 1
    assert request.state[RETRY_STATE_KEY] == 1


@pytest.mark.asyncio
async def test_retry_middleware_respects_exception_types():
    middleware = RetryMiddleware(RequestRetryConfig(enabled=True, attempts=1, exceptions=(asyncio.TimeoutError,)))
    request = Request(url="https://example.com")

    with pytest.raises(StopRequestProcessing):
        await middleware(request=request, exc=asyncio.TimeoutError(), send_request=_noop_send)


@pytest.mark.asyncio
async def test_retry_middleware_stops_after_max_attempts():
    middleware = RetryMiddleware(RequestRetryConfig(enabled=True, attempts=1, statuses=(500,)))
    request = Request(url="https://example.com")
    request.state[RETRY_STATE_KEY] = 1

    exc = HTTPException(
        url="https://example.com",
        method="GET",
        status_code=500,
        headers={},
        message="boom",
    )

    await middleware(request=request, exc=exc, send_request=_noop_send)


@pytest.mark.asyncio
async def test_retry_middleware_disabled():
    middleware = RetryMiddleware(
        RequestRetryConfig(enabled=False, attempts=3, statuses=(500,), exceptions=(RuntimeError,))
    )
    request = Request(url="https://example.com")

    await middleware(
        request=request,
        exc=HTTPException(
            url="https://example.com",
            method="GET",
            status_code=500,
            headers={},
            message="boom",
        ),
        send_request=_noop_send,
    )


class RetryScraper:
    def __init__(self, url: str):
        self.url = url
        self.callbacks = 0
        self.errbacks = 0

    async def __call__(self, send_request: SendRequest):
        await send_request(
            Request(
                url=self.url,
                callback=self.handle_response,
                errback=self.handle_error,
            )
        )

    async def handle_response(self, response: Response):
        self.callbacks += 1

    async def handle_error(self, exc: Exception):
        self.errbacks += 1


@pytest.mark.asyncio
async def test_retry_middleware_integration(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add(
        "https://api.test.com/flaky",
        handler=lambda _: MockResponse(status=502),
        repeat=2,
    )
    mock_aioscraper.server.add("https://api.test.com/flaky", handler=lambda _: {"ok": True})

    scraper = RetryScraper("https://api.test.com/flaky")
    mock_aioscraper(scraper)
    mock_aioscraper.config = Config(
        session=SessionConfig(retry=RequestRetryConfig(enabled=True, attempts=2, statuses=(502,)))
    )

    async with mock_aioscraper:
        await mock_aioscraper.start()

    assert scraper.callbacks == 1
    assert scraper.errbacks == 0
    mock_aioscraper.server.assert_all_routes_handled()


@pytest.mark.asyncio
async def test_retry_middleware_exhausts_attempts(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add(
        "https://api.test.com/always-bad",
        handler=lambda _: MockResponse(status=502),
        repeat=3,
    )

    scraper = RetryScraper("https://api.test.com/always-bad")
    mock_aioscraper(scraper)
    mock_aioscraper.config = Config(
        session=SessionConfig(retry=RequestRetryConfig(enabled=True, attempts=2, statuses=(502,)))
    )

    async with mock_aioscraper:
        await mock_aioscraper.start()

    assert scraper.callbacks == 0
    assert scraper.errbacks == 1
    mock_aioscraper.server.assert_all_routes_handled()
