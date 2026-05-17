import logging

from aioscraper._helpers.http import parse_retry_after
from aioscraper.config import RequestRetryConfig
from aioscraper.exceptions import HTTPException
from aioscraper.types import Request, RequestHandler, Response, SendRequest

RETRY_STATE_KEY = "_aioscraper_retry_attempts"

logger = logging.getLogger(__name__)


class RetryMiddleware:
    """Request middleware that retries failed requests based on configuration."""

    def __init__(self, config: RequestRetryConfig, send_request: SendRequest):
        self._enabled = config.enabled
        self._attempts = max(0, config.attempts)
        self._retry_delay_factory = config.delay_factory
        self._statuses = set(config.statuses)
        self._exception_types = tuple(config.exceptions)
        self._send_request = send_request

        if self._enabled:
            logger.info(
                "Retry middleware enabled: attempts=%d, backoff=%s, base_delay=%0.10g, max_delay=%0.10g, "
                "statuses=%s, exceptions=%s",
                self._attempts,
                config.backoff,
                config.base_delay,
                config.max_delay,
                ",".join(map(str, sorted(self._statuses))),
                ",".join(exc.__module__ + "." + exc.__qualname__ for exc in self._exception_types),
            )

    async def __call__(self, call_next: RequestHandler, request: Request) -> Response | None:
        try:
            return await call_next(request)
        except Exception as exc:
            if not self._enabled or not self._should_retry(exc):
                raise

            attempts_used = request.state.get(RETRY_STATE_KEY, 0)
            if attempts_used >= self._attempts:
                raise

            attempts = request.state[RETRY_STATE_KEY] = attempts_used + 1

            if retry_after_delay := parse_retry_after(exc):
                request.delay = min(600.0, round(retry_after_delay, 6))
            else:
                request.delay = round(self._retry_delay_factory(attempts), 6)

            await self._send_request(request)
            return None

    def _should_retry(self, exc: Exception) -> bool:
        if self._statuses and isinstance(exc, HTTPException) and exc.status_code in self._statuses:
            return True

        if self._exception_types and isinstance(exc, self._exception_types):
            return True

        return False
