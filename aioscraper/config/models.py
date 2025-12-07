import asyncio
import logging
import random
import ssl as ssl_module
from enum import StrEnum, auto
from dataclasses import dataclass
from typing import Callable


@dataclass(slots=True, frozen=True)
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
    attempts: int = 3
    backoff: BackoffStrategy = BackoffStrategy.EXPONENTIAL_JITTER
    base_delay: float = 0.5
    max_delay: float = 30.0
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
                return min(self.max_delay, (delay / 2) + random.uniform(0, delay / 2))

            return _factory

        return lambda _: self.base_delay


class HttpBackend(StrEnum):
    AIOHTTP = "aiohttp"
    HTTPX = "httpx"


@dataclass(slots=True, frozen=True)
class SessionConfig:
    """HTTP session settings shared by every request.

    Args:
        timeout (float): Request timeout in seconds
        delay (float): Delay between requests in seconds
        ssl (ssl.SSLContext | bool): SSL handling; bool toggles verification, SSLContext can carry custom CAs
        proxy (str | dict[str, str | None] | None): Default proxy passed to the HTTP client
        http_backend (HttpBackend | None): Force ``aiohttp``/``httpx``; ``None`` lets the factory auto-detect
        retry (RequestRetryConfig): Controls built-in retry middleware behaviour
    """

    timeout: float = 60.0
    delay: float = 0.0
    ssl: ssl_module.SSLContext | bool = True
    proxy: str | dict[str, str | None] | None = None
    http_backend: HttpBackend | None = None
    retry: RequestRetryConfig = RequestRetryConfig()


@dataclass(slots=True, frozen=True)
class SchedulerConfig:
    """
    Configuration for request scheduler.

    Args:
        concurrent_requests (int): Maximum number of concurrent requests
        pending_requests (int): Number of pending requests to maintain
        close_timeout (float | None): Timeout for closing scheduler in seconds
    """

    concurrent_requests: int = 64
    pending_requests: int = 1
    close_timeout: float | None = 0.1


@dataclass(slots=True, frozen=True)
class ExecutionConfig:
    """
    Configuration for execution.

    Args:
        timeout (float | None): Overall execution timeout in seconds
        shutdown_timeout (float): Timeout for graceful shutdown in seconds
        shutdown_check_interval (float): Interval between shutdown checks in seconds
        log_level (int): Log level when a timeout occurs
    """

    timeout: float | None = None
    shutdown_timeout: float = 0.1
    shutdown_check_interval: float = 0.1
    log_level: int = logging.ERROR


@dataclass(slots=True, frozen=True)
class PipelineConfig:
    """
    Configuration for pipelines.

    Args:
        strict (bool): Raise an exception if a pipeline for an item is missing
    """

    strict: bool = True


@dataclass(slots=True, frozen=True)
class Config:
    "Main configuration class that combines all configuration components."

    session: SessionConfig = SessionConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
    execution: ExecutionConfig = ExecutionConfig()
    pipeline: PipelineConfig = PipelineConfig()
