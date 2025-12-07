import asyncio
import logging

from ..config import RequestRetryConfig
from ..exceptions import HTTPException, StopRequestProcessing
from ..types import Request, SendRequest

RETRY_STATE_KEY = "_aioscraper_retry_attempts"

logger = logging.getLogger(__name__)


class RetryMiddleware:
    """Exception middleware that retries failed requests based on configuration."""

    def __init__(self, config: RequestRetryConfig):
        self._enabled = config.enabled
        self._attempts = max(0, config.attempts)
        self._delay = config.delay
        self._statuses = set(config.statuses)
        self._exception_types = tuple(config.exceptions)
        self._stop_processing = config.middleware.stop_processing

        if self._enabled:
            logger.info("retry middleware enabled")

    async def __call__(self, request: Request, exc: Exception, send_request: SendRequest):
        if not self._enabled or not self._should_retry(exc):
            return

        attempts_used = request.state.get(RETRY_STATE_KEY, 0)
        if attempts_used >= self._attempts:
            return

        request.state[RETRY_STATE_KEY] = attempts_used + 1
        await asyncio.sleep(self._delay)
        await send_request(request)
        if self._stop_processing:
            raise StopRequestProcessing

    def _should_retry(self, exc: Exception) -> bool:
        if self._statuses and isinstance(exc, HTTPException) and exc.status_code in self._statuses:
            return True

        if self._exception_types and isinstance(exc, self._exception_types):
            return True

        return False
