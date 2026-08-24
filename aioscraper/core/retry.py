import logging

from aioscraper._helpers.http import parse_retry_after
from aioscraper.config import RequestRetryConfig
from aioscraper.exceptions import HTTPException
from aioscraper.types import Request

logger = logging.getLogger(__name__)


class RetryPolicy:
    """Decides whether a failed attempt is admitted again, and after how long.

    Args:
        config (RequestRetryConfig): Retry settings to apply.
    """

    def __init__(self, config: RequestRetryConfig):
        self._enabled = config.enabled
        self._attempts = max(0, config.attempts)
        self._delay_factory = config.delay_factory
        self._max_retry_after = config.max_retry_after
        self._statuses = set(config.statuses)
        self._exception_types = tuple(config.exceptions)
        self._methods = frozenset(method.upper() for method in config.methods)
        self._should_retry = config.should_retry

        if self._enabled:
            logger.info(
                "Retry enabled: attempts=%d, backoff=%s, base_delay=%0.10g, max_delay=%0.10g, "
                "statuses=%s, exceptions=%s, methods=%s",
                self._attempts,
                config.backoff,
                config.base_delay,
                config.max_delay,
                ",".join(map(str, sorted(self._statuses))),
                ",".join(exc.__module__ + "." + exc.__qualname__ for exc in self._exception_types),
                ",".join(sorted(self._methods)),
            )

    def next_delay(self, request: Request, exc: Exception, retries: int) -> float | None:
        """Decide how long to wait before admitting the request again.

        Args:
            request (Request): The request that failed.
            exc (Exception): The failure raised by dispatch.
            retries (int): How many times this request was already re-admitted.

        Returns:
            float | None: Delay in seconds, or ``None`` when the request must not be retried.
        """
        if not self._enabled or retries >= self._attempts:
            return None

        if not self._is_retryable(request) or not self._triggers(request, exc, retries):
            return None

        if retry_after := parse_retry_after(exc):
            return min(self._max_retry_after, round(retry_after, 6))

        return round(self._delay_factory(retries + 1), 6)

    def _is_retryable(self, request: Request) -> bool:
        # a replayed non-idempotent request can duplicate a server-side effect
        if request.retryable is not None:
            return request.retryable

        return request.method.upper() in self._methods

    def _triggers(self, request: Request, exc: Exception, retries: int) -> bool:
        # runs after the method check above: the hook can narrow what is retried, never widen it
        if self._should_retry is not None and (verdict := self._should_retry(request, exc, retries)) is not None:
            return verdict

        if self._statuses and isinstance(exc, HTTPException) and exc.status_code in self._statuses:
            return True

        return bool(self._exception_types) and isinstance(exc, self._exception_types)
