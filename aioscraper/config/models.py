import asyncio
import logging
import random
import ssl as ssl_module
from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Callable, Hashable

from aioscraper.types import Request

from .field_validators import ProxyValidator, RangeValidator
from .model_validator import field, validate


@dataclass(slots=True, frozen=True)
@validate
class MiddlewareConfig:
    """Common options shared by built-in middlewares.

    Args:
        priority (int): Execution order (lower values run earlier).
        stop_processing (bool): Whether the middleware should raise
            :class:`StopRequestProcessing` / :class:`StopMiddlewareProcessing`
            automatically after running.
    """

    priority: int = 100
    stop_processing: bool = False


@dataclass(slots=True, frozen=True)
@validate
class AdaptiveRateLimitConfig:
    """Configuration for adaptive rate limiting using EWMA + AIMD.

    Adaptively adjusts request intervals based on server response patterns.
    Uses EWMA (Exponentially Weighted Moving Average) for latency tracking
    and AIMD (Additive Increase Multiplicative Decrease) for interval adjustment.

    Args:
        min_interval (float): Minimum allowed interval between requests (seconds).
        max_interval (float): Maximum allowed interval between requests (seconds).
        increase_factor (float): Multiplicative factor for interval increase on failure (must be > 1.0).
        decrease_step (float): Additive step for interval decrease on success (seconds).
        success_threshold (int): Number of consecutive successes before decreasing interval.
        ewma_alpha (float): EWMA smoothing factor for latency (0 < alpha <= 1, higher = more weight to recent).
        respect_retry_after (bool): Whether to use Retry-After header as interval override.
        inherit_retry_triggers (bool): Whether to use RequestRetryConfig statuses/exceptions as triggers.
        custom_trigger_statuses (tuple[int, ...]): Additional HTTP statuses to trigger adaptive slowdown.
        custom_trigger_exceptions (tuple[type[BaseException], ...]):
            Additional exception types to trigger adaptive slowdown.
    """

    min_interval: float = field(default=0.001, validator=RangeValidator(min_value=0.001))
    max_interval: float = field(default=5.0, validator=RangeValidator(min_value=0.001))
    increase_factor: float = field(default=2.0, validator=RangeValidator(min_value=1.0))
    decrease_step: float = field(default=0.01, validator=RangeValidator(min_value=0.001))
    success_threshold: int = field(default=5, validator=RangeValidator(min_value=1))
    ewma_alpha: float = field(default=0.3, validator=RangeValidator(min_value=0.0, max_value=1.0))
    respect_retry_after: bool = True
    inherit_retry_triggers: bool = True
    custom_trigger_statuses: tuple[int, ...] = ()
    custom_trigger_exceptions: tuple[type[BaseException], ...] = ()


@dataclass(slots=True, frozen=True)
@validate
class RateLimitConfig:
    """
    Configuration for rate limiting.

    Args:
        enabled (bool): Toggle rate limiting on or off.
        group_by (Callable[[Request], tuple[Hashable, float]] | None): Function to group requests by.
        default_interval (float): Default interval for group.
        cleanup_timeout (float): Timeout in seconds before cleaning up an idle request group.
        adaptive (AdaptiveRateLimitConfig | None): Adaptive rate limiting configuration (EWMA + AIMD).
    """

    enabled: bool = False
    group_by: Callable[[Request], tuple[Hashable, float]] | None = field(default=None, skip_validation=True)
    default_interval: float = field(default=0.0, validator=RangeValidator(min_value=0.0))
    cleanup_timeout: float = field(default=60.0, validator=RangeValidator(min_value=0.1))
    adaptive: AdaptiveRateLimitConfig | None = None


class BackoffStrategy(StrEnum):
    """
    Backoff strategy for retries.

    Attributes:
        CONSTANT: Constant backoff
        LINEAR: Linear backoff
        EXPONENTIAL: Exponential backoff
        EXPONENTIAL_JITTER: Exponential backoff with jitter
    """

    CONSTANT = auto()
    LINEAR = auto()
    EXPONENTIAL = auto()
    EXPONENTIAL_JITTER = auto()


@dataclass(slots=True, frozen=True)
@validate
class RequestRetryConfig:
    """Retry behaviour applied by the built-in retry middleware.

    Args:
        enabled (bool): Toggle retries on or off.
        attempts (int): Maximum number of retry attempts per request.
        backoff (BackoffStrategy): Backoff strategy for retries.
        base_delay (float): Base delay between retries in seconds.
        max_delay (float): Maximum delay between retries in seconds.
        statuses (tuple[int, ...]): HTTP status codes that should trigger a retry.
        exceptions (tuple[type[BaseException], ...]): Exception types that should trigger a retry.
        middleware (MiddlewareConfig): Overrides for how the retry middleware
            is registered (priority/stop behaviour).
    """

    enabled: bool = False
    attempts: int = field(default=3, validator=RangeValidator(min_value=1))
    backoff: BackoffStrategy = BackoffStrategy.EXPONENTIAL_JITTER
    base_delay: float = field(default=0.5, validator=RangeValidator(min_value=0.001))
    max_delay: float = field(default=30.0, validator=RangeValidator(min_value=0.001))
    statuses: tuple[int, ...] = (500, 502, 503, 504, 522, 524, 408, 429)
    exceptions: tuple[type[BaseException], ...] = (asyncio.TimeoutError,)
    middleware: MiddlewareConfig = MiddlewareConfig(stop_processing=True)

    @property
    def delay_factory(self) -> Callable[[int], float]:
        if self.backoff == BackoffStrategy.LINEAR:
            return lambda attempt: self.base_delay * attempt
        elif self.backoff == BackoffStrategy.EXPONENTIAL:
            return lambda attempt: min(self.max_delay, self.base_delay * (2**attempt))
        elif self.backoff == BackoffStrategy.EXPONENTIAL_JITTER:

            def _factory(attempt: int) -> float:
                delay = self.base_delay * (2**attempt)
                return min(self.max_delay, (delay / 2) + random.uniform(0, delay / 2))  # noqa: S311

            return _factory

        return lambda _: self.base_delay


class HttpBackend(StrEnum):
    AIOHTTP = "aiohttp"
    HTTPX = "httpx"


@dataclass(slots=True, frozen=True)
@validate
class SessionConfig:
    """HTTP session settings shared by every request.

    Args:
        timeout (float): Request timeout in seconds
        ssl (ssl.SSLContext | bool): SSL handling; bool toggles verification, SSLContext can carry custom CAs
        proxy (str | dict[str, str | None] | None): Default proxy passed to the HTTP client
        http_backend (HttpBackend | None): Force ``aiohttp``/``httpx``; ``None`` lets the factory auto-detect
        retry (RequestRetryConfig): Controls built-in retry middleware behaviour
        rate_limit (RateLimitConfig): Controls built-in rate limiting behaviour
    """

    timeout: float = field(default=60.0, validator=RangeValidator(min_value=0.001))
    ssl: ssl_module.SSLContext | bool = True
    proxy: str | dict[str, str | None] | None = field(default=None, validator=ProxyValidator({"http", "https"}))
    http_backend: HttpBackend | None = None
    retry: RequestRetryConfig = RequestRetryConfig()
    rate_limit: RateLimitConfig = RateLimitConfig()


@dataclass(slots=True, frozen=True)
@validate
class SchedulerConfig:
    """
    Configuration for request scheduler.

    Args:
        concurrent_requests (int): Maximum number of concurrent requests
        pending_requests (int): Number of pending requests to maintain
        close_timeout (float | None): Timeout for closing scheduler in seconds
        ready_queue_max_size (int): Maximum size of the ready queue (0 for unlimited)
    """

    concurrent_requests: int = field(default=64, validator=RangeValidator(min_value=1))
    pending_requests: int = field(default=1, validator=RangeValidator(min_value=1))
    close_timeout: float | None = field(default=0.1, validator=RangeValidator(min_value=0.01))
    ready_queue_max_size: int = field(default=0, validator=RangeValidator(min_value=0))


@dataclass(slots=True, frozen=True)
@validate
class ExecutionConfig:
    """
    Configuration for execution.

    Args:
        timeout (float | None): Overall execution timeout in seconds
        shutdown_timeout (float): Timeout for graceful shutdown in seconds
        log_level (int): Log level for timeout events (e.g., logging.ERROR, logging.WARNING).
            Defaults to logging.ERROR.
    """

    timeout: float | None = field(default=None, validator=RangeValidator(min_value=0.01))
    shutdown_timeout: float = field(default=0.1, validator=RangeValidator(min_value=0.001))
    shutdown_check_interval: float = field(default=0.1, validator=RangeValidator(min_value=0.01))
    log_level: int = logging.ERROR


@dataclass(slots=True, frozen=True)
@validate
class PipelineConfig:
    """
    Configuration for pipelines.

    Args:
        strict (bool): Raise an exception if a pipeline for an item is missing
    """

    strict: bool = True


@dataclass(slots=True, frozen=True)
@validate
class Config:
    "Main configuration class that combines all configuration components."

    session: SessionConfig = SessionConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
    execution: ExecutionConfig = ExecutionConfig()
    pipeline: PipelineConfig = PipelineConfig()
