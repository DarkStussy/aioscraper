import asyncio
from unittest.mock import patch
import pytest

from aioscraper.config import BackoffStrategy, Config, RequestRetryConfig, SessionConfig
from aioscraper.exceptions import HTTPException, StopRequestProcessing
from aioscraper.middlewares.retry import RETRY_STATE_KEY, RetryMiddleware
from aioscraper.types import Request, Response, SendRequest
from tests.mocks import MockAIOScraper, MockResponse


async def _noop_send(req: Request):
    return req


@pytest.mark.asyncio
async def test_retry_middleware_retries_on_status():
    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=2,
            base_delay=0.1,
            max_delay=0.1,
            statuses=(502,),
            exceptions=(),
        )
    )
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
    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=1,
            base_delay=0.1,
            max_delay=0.1,
            exceptions=(asyncio.TimeoutError,),
            backoff=BackoffStrategy.CONSTANT,
        )
    )
    request = Request(url="https://example.com")

    with pytest.raises(StopRequestProcessing):
        await middleware(request=request, exc=asyncio.TimeoutError(), send_request=_noop_send)


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
        )
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

    await middleware(request=request, exc=exc, send_request=_noop_send)


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
        )
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


@pytest.mark.asyncio
async def test_retry_middleware_constant_backoff():
    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=2,
            base_delay=0.1,
            backoff=BackoffStrategy.CONSTANT,
            statuses=(500,),
        )
    )
    request = Request(url="https://example.com")
    exc = HTTPException(url="https://example.com", method="GET", status_code=500, headers={}, message="boom")

    received_request = None

    async def mock_send_request(req: Request):
        nonlocal received_request
        received_request = req
        raise StopRequestProcessing  # The middleware raises this, so our mock should too for proper testing.

    with pytest.raises(StopRequestProcessing):
        await middleware(request=request, exc=exc, send_request=mock_send_request)

    assert received_request is not None
    assert received_request.delay == 0.1


@pytest.mark.asyncio
async def test_retry_middleware_linear_backoff():
    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=3,
            base_delay=0.1,
            backoff=BackoffStrategy.LINEAR,
            statuses=(500,),
        )
    )
    request = Request(url="https://example.com")
    exc = HTTPException(url="https://example.com", method="GET", status_code=500, headers={}, message="boom")

    received_requests = []

    async def mock_send_request(req: Request):
        received_requests.append(req)
        raise StopRequestProcessing

    with pytest.raises(StopRequestProcessing):
        await middleware(request=request, exc=exc, send_request=mock_send_request)

    assert len(received_requests) == 1
    assert received_requests[0].delay == 0.1

    # Second attempt
    request.state[RETRY_STATE_KEY] = 1  # Manually set state for next attempt
    with pytest.raises(StopRequestProcessing):
        await middleware(request=request, exc=exc, send_request=mock_send_request)

    assert len(received_requests) == 2
    assert received_requests[1].delay == 0.2


@pytest.mark.asyncio
async def test_retry_middleware_exponential_backoff():
    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=4,
            base_delay=0.1,
            max_delay=1.0,
            backoff=BackoffStrategy.EXPONENTIAL,
            statuses=(500,),
        )
    )
    request = Request(url="https://example.com")
    exc = HTTPException(url="https://example.com", method="GET", status_code=500, headers={}, message="boom")

    received_requests = []

    async def mock_send_request(req: Request):
        received_requests.append(req)
        raise StopRequestProcessing

    with pytest.raises(StopRequestProcessing):
        await middleware(request=request, exc=exc, send_request=mock_send_request)

    assert len(received_requests) == 1
    assert received_requests[0].delay == 0.2  # 0.1 * (2**1)

    # Second attempt
    request.state[RETRY_STATE_KEY] = 1  # Manually set state for next attempt
    with pytest.raises(StopRequestProcessing):
        await middleware(request=request, exc=exc, send_request=mock_send_request)

    assert len(received_requests) == 2
    assert received_requests[1].delay == 0.4  # 0.1 * (2**2)

    # Third attempt
    request.state[RETRY_STATE_KEY] = 2  # Manually set state for next attempt
    with pytest.raises(StopRequestProcessing):
        await middleware(request=request, exc=exc, send_request=mock_send_request)

    assert len(received_requests) == 3
    assert received_requests[2].delay == 0.8  # 0.1 * (2**3)


@pytest.mark.asyncio
async def test_retry_middleware_exponential_backoff_with_max_delay():
    middleware = RetryMiddleware(
        RequestRetryConfig(
            enabled=True,
            attempts=2,
            base_delay=0.5,
            max_delay=0.8,
            backoff=BackoffStrategy.EXPONENTIAL,
            statuses=(500,),
        )
    )
    request = Request(url="https://example.com")
    exc = HTTPException(url="https://example.com", method="GET", status_code=500, headers={}, message="boom")

    received_request = None

    async def mock_send_request(req: Request):
        nonlocal received_request
        received_request = req
        raise StopRequestProcessing

    with pytest.raises(StopRequestProcessing):
        await middleware(request=request, exc=exc, send_request=mock_send_request)

    assert received_request is not None
    assert received_request.delay == 0.8  # min(0.8, 0.5 * (2**1))


@pytest.mark.asyncio
async def test_retry_middleware_exponential_jitter_backoff():
    with patch("random.uniform", return_value=0.05):
        middleware = RetryMiddleware(
            RequestRetryConfig(
                enabled=True,
                attempts=2,
                base_delay=0.1,
                max_delay=1.0,
                backoff=BackoffStrategy.EXPONENTIAL_JITTER,
                statuses=(500,),
            )
        )
        request = Request(url="https://example.com")
        exc = HTTPException(url="https://example.com", method="GET", status_code=500, headers={}, message="boom")

        received_request = None

        async def mock_send_request(req: Request):
            nonlocal received_request
            received_request = req
            raise StopRequestProcessing

        with pytest.raises(StopRequestProcessing):
            await middleware(request=request, exc=exc, send_request=mock_send_request)

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
        session=SessionConfig(
            retry=RequestRetryConfig(
                enabled=True,
                attempts=2,
                base_delay=0.05,
                statuses=(502,),
                backoff=BackoffStrategy.CONSTANT,
            )
        )
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
        session=SessionConfig(
            retry=RequestRetryConfig(
                enabled=True,
                attempts=2,
                base_delay=0.05,
                statuses=(502,),
                backoff=BackoffStrategy.CONSTANT,
            )
        )
    )

    async with mock_aioscraper:
        await mock_aioscraper.start()

    assert scraper.callbacks == 0
    assert scraper.errbacks == 1
    mock_aioscraper.server.assert_all_routes_handled()
