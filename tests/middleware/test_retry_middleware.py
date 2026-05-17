import asyncio
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import patch

import pytest

from aioscraper.config import BackoffStrategy, Config, RequestRetryConfig, SessionConfig
from aioscraper.exceptions import HTTPException
from aioscraper.middlewares.retry import RETRY_STATE_KEY, RetryMiddleware
from aioscraper.types import Request, RequestHandler, Response, SendRequest
from tests.mocks import MockAIOScraper, MockResponse


async def _noop_send(req: Request) -> Request:
    return req


def _call_next_raising(exc: Exception) -> RequestHandler:
    async def call_next(request: Request) -> Response | None:
        raise exc

    return call_next


@pytest.mark.asyncio
async def test_retry_middleware_retries_on_status():
    send_calls = 0

    async def send(req: Request) -> Request:
        nonlocal send_calls
        send_calls += 1
        return req

    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=2,
            base_delay=0.1,
            max_delay=0.1,
            statuses=(502,),
            exceptions=(),
        ),
        send_request=send,
    )
    request = Request(url="https://example.com")

    exc = HTTPException(
        url="https://example.com",
        method="GET",
        status_code=502,
        headers={},
        message="bad gateway",
    )

    result = await middleware(_call_next_raising(exc), request)

    assert result is None
    assert send_calls == 1
    assert request.state[RETRY_STATE_KEY] == 1


@pytest.mark.asyncio
async def test_retry_middleware_respects_exception_types():
    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=1,
            base_delay=0.1,
            max_delay=0.1,
            exceptions=(asyncio.TimeoutError,),
            backoff=BackoffStrategy.CONSTANT,
        ),
        send_request=_noop_send,
    )
    request = Request(url="https://example.com")

    result = await middleware(_call_next_raising(asyncio.TimeoutError()), request)

    assert result is None


@pytest.mark.asyncio
async def test_retry_middleware_stops_after_max_attempts():
    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=1,
            base_delay=0.1,
            max_delay=0.1,
            statuses=(500,),
            backoff=BackoffStrategy.CONSTANT,
        ),
        send_request=_noop_send,
    )
    request = Request(url="https://example.com")
    request.state[RETRY_STATE_KEY] = 1

    exc = HTTPException(
        url="https://example.com",
        method="GET",
        status_code=500,
        headers={},
        message="boom",
    )

    with pytest.raises(HTTPException):
        await middleware(_call_next_raising(exc), request)


@pytest.mark.asyncio
async def test_retry_middleware_disabled():
    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=False,
            attempts=3,
            statuses=(500,),
            base_delay=0.1,
            max_delay=0.1,
            exceptions=(RuntimeError,),
            backoff=BackoffStrategy.CONSTANT,
        ),
        send_request=_noop_send,
    )
    request = Request(url="https://example.com")

    exc = HTTPException(
        url="https://example.com",
        method="GET",
        status_code=500,
        headers={},
        message="boom",
    )

    with pytest.raises(HTTPException):
        await middleware(_call_next_raising(exc), request)


@pytest.mark.asyncio
async def test_retry_middleware_unmatched_exception_is_propagated():
    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=2,
            base_delay=0.1,
            statuses=(500,),
            exceptions=(),
            backoff=BackoffStrategy.CONSTANT,
        ),
        send_request=_noop_send,
    )
    request = Request(url="https://example.com")

    with pytest.raises(RuntimeError):
        await middleware(_call_next_raising(RuntimeError("boom")), request)


@pytest.mark.asyncio
async def test_retry_middleware_constant_backoff():
    received_request: Request | None = None

    async def send(req: Request) -> Request:
        nonlocal received_request
        received_request = req
        return req

    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=2,
            base_delay=0.1,
            backoff=BackoffStrategy.CONSTANT,
            statuses=(500,),
        ),
        send_request=send,
    )
    request = Request(url="https://example.com")
    exc = HTTPException(url="https://example.com", method="GET", status_code=500, headers={}, message="boom")

    result = await middleware(_call_next_raising(exc), request)

    assert result is None
    assert received_request is not None
    assert received_request.delay == 0.1


@pytest.mark.asyncio
async def test_retry_middleware_linear_backoff():
    received_requests: list[Request] = []

    async def send(req: Request) -> Request:
        received_requests.append(req)
        return req

    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=3,
            base_delay=0.1,
            backoff=BackoffStrategy.LINEAR,
            statuses=(500,),
        ),
        send_request=send,
    )
    request = Request(url="https://example.com")
    exc = HTTPException(url="https://example.com", method="GET", status_code=500, headers={}, message="boom")

    await middleware(_call_next_raising(exc), request)

    assert len(received_requests) == 1
    assert received_requests[0].delay == 0.1

    request.state[RETRY_STATE_KEY] = 1
    await middleware(_call_next_raising(exc), request)

    assert len(received_requests) == 2
    assert received_requests[1].delay == 0.2


@pytest.mark.asyncio
async def test_retry_middleware_exponential_backoff():
    received_requests: list[Request] = []

    async def send(req: Request) -> Request:
        received_requests.append(req)
        return req

    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=4,
            base_delay=0.1,
            max_delay=1.0,
            backoff=BackoffStrategy.EXPONENTIAL,
            statuses=(500,),
        ),
        send_request=send,
    )
    request = Request(url="https://example.com")
    exc = HTTPException(url="https://example.com", method="GET", status_code=500, headers={}, message="boom")

    await middleware(_call_next_raising(exc), request)

    assert len(received_requests) == 1
    assert received_requests[0].delay == 0.2  # 0.1 * (2**1)

    request.state[RETRY_STATE_KEY] = 1
    await middleware(_call_next_raising(exc), request)

    assert len(received_requests) == 2
    assert received_requests[1].delay == 0.4  # 0.1 * (2**2)

    request.state[RETRY_STATE_KEY] = 2
    await middleware(_call_next_raising(exc), request)

    assert len(received_requests) == 3
    assert received_requests[2].delay == 0.8  # 0.1 * (2**3)


@pytest.mark.asyncio
async def test_retry_middleware_exponential_backoff_with_max_delay():
    received_request: Request | None = None

    async def send(req: Request) -> Request:
        nonlocal received_request
        received_request = req
        return req

    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=2,
            base_delay=0.5,
            max_delay=0.8,
            backoff=BackoffStrategy.EXPONENTIAL,
            statuses=(500,),
        ),
        send_request=send,
    )
    request = Request(url="https://example.com")
    exc = HTTPException(url="https://example.com", method="GET", status_code=500, headers={}, message="boom")

    await middleware(_call_next_raising(exc), request)

    assert received_request is not None
    assert received_request.delay == 0.8  # min(0.8, 0.5 * (2**1))


@pytest.mark.asyncio
async def test_retry_middleware_exponential_jitter_backoff():
    received_request: Request | None = None

    async def send(req: Request) -> Request:
        nonlocal received_request
        received_request = req
        return req

    with patch("random.uniform", return_value=0.05):
        middleware = RetryMiddleware(
            RequestRetryConfig(
                enabled=True,
                attempts=2,
                base_delay=0.1,
                max_delay=1.0,
                backoff=BackoffStrategy.EXPONENTIAL_JITTER,
                statuses=(500,),
            ),
            send_request=send,
        )
        request = Request(url="https://example.com")
        exc = HTTPException(url="https://example.com", method="GET", status_code=500, headers={}, message="boom")

        await middleware(_call_next_raising(exc), request)

        # delay = 0.1 * (2**1) = 0.2
        # (delay / 2) + random.uniform(0, delay / 2) = 0.1 + 0.05 = 0.15
        assert received_request is not None
        assert received_request.delay == 0.15


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
            ),
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
        session=SessionConfig(
            retry=RequestRetryConfig(
                enabled=True,
                attempts=2,
                base_delay=0.05,
                statuses=(502,),
                backoff=BackoffStrategy.CONSTANT,
            ),
        ),
    )

    async with mock_aioscraper:
        await mock_aioscraper.wait()

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
        session=SessionConfig(
            retry=RequestRetryConfig(
                enabled=True,
                attempts=2,
                base_delay=0.05,
                statuses=(502,),
                backoff=BackoffStrategy.CONSTANT,
            ),
        ),
    )

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert scraper.callbacks == 0
    assert scraper.errbacks == 1
    mock_aioscraper.server.assert_all_routes_handled()


@pytest.mark.asyncio
async def test_retry_middleware_respects_retry_after_seconds():
    """Test that Retry-After header (in seconds) overrides backoff strategy."""
    received_request: Request | None = None

    async def send(req: Request) -> Request:
        nonlocal received_request
        received_request = req
        return req

    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=2,
            base_delay=1.0,
            backoff=BackoffStrategy.CONSTANT,
            statuses=(429,),
        ),
        send_request=send,
    )
    request = Request(url="https://example.com")
    exc = HTTPException(
        url="https://example.com",
        method="GET",
        status_code=429,
        headers={"Retry-After": "5"},
        message="rate limited",
    )

    await middleware(_call_next_raising(exc), request)

    assert received_request is not None
    assert received_request.delay == 5.0


@pytest.mark.asyncio
async def test_retry_middleware_respects_retry_after_http_date():
    """Test that Retry-After header (HTTP-date) overrides backoff strategy."""
    received_request: Request | None = None

    async def send(req: Request) -> Request:
        nonlocal received_request
        received_request = req
        return req

    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=2,
            base_delay=1.0,
            backoff=BackoffStrategy.CONSTANT,
            statuses=(503,),
        ),
        send_request=send,
    )
    request = Request(url="https://example.com")

    retry_time = datetime.now(UTC) + timedelta(seconds=10)
    exc = HTTPException(
        url="https://example.com",
        method="GET",
        status_code=503,
        headers={"Retry-After": format_datetime(retry_time, usegmt=True)},
        message="service unavailable",
    )

    await middleware(_call_next_raising(exc), request)

    assert received_request is not None
    # Allow 1 second tolerance for test execution time
    assert received_request.delay is not None
    assert 9.0 <= received_request.delay <= 11.0


@pytest.mark.asyncio
async def test_retry_middleware_retry_after_case_insensitive():
    """Test that retry-after header is case-insensitive."""
    received_request: Request | None = None

    async def send(req: Request) -> Request:
        nonlocal received_request
        received_request = req
        return req

    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=2,
            base_delay=1.0,
            backoff=BackoffStrategy.CONSTANT,
            statuses=(429,),
        ),
        send_request=send,
    )
    request = Request(url="https://example.com")
    exc = HTTPException(
        url="https://example.com",
        method="GET",
        status_code=429,
        headers={"retry-after": "3"},
        message="rate limited",
    )

    await middleware(_call_next_raising(exc), request)

    assert received_request is not None
    assert received_request.delay == 3.0


@pytest.mark.asyncio
async def test_retry_middleware_fallback_to_backoff_without_retry_after():
    """Test that backoff is used when Retry-After is not present."""
    received_request: Request | None = None

    async def send(req: Request) -> Request:
        nonlocal received_request
        received_request = req
        return req

    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=2,
            base_delay=2.0,
            backoff=BackoffStrategy.CONSTANT,
            statuses=(500,),
        ),
        send_request=send,
    )
    request = Request(url="https://example.com")
    exc = HTTPException(
        url="https://example.com",
        method="GET",
        status_code=500,
        headers={},
        message="internal error",
    )

    await middleware(_call_next_raising(exc), request)

    assert received_request is not None
    assert received_request.delay == 2.0
