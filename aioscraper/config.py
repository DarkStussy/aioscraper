import asyncio
import importlib
import logging
import ssl as ssl_module
from enum import StrEnum
from dataclasses import dataclass

from . import env_parser


class HttpBackend(StrEnum):
    AIOHTTP = "aiohttp"
    HTTPX = "httpx"


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


@dataclass(slots=True, frozen=True)
class RequestRetryConfig:
    """Retry behaviour applied by the built-in retry middleware.

    Args:
        enabled (bool): Toggle retries on or off.
        attempts (int): Maximum number of retry attempts per request.
        delay (float): Delay between retries in seconds.
        statuses (tuple[int, ...]): HTTP status codes that should trigger a retry.
        exceptions (tuple[type[BaseException], ...]): Exception types that should trigger a retry.
        middleware (MiddlewareConfig): Overrides for how the retry middleware
            is registered (priority/stop behaviour).
    """

    enabled: bool = False
    attempts: int = 3
    delay: float = 0.1
    statuses: tuple[int, ...] = (500, 502, 503, 504, 522, 524, 408, 429)
    exceptions: tuple[type[BaseException], ...] = (asyncio.TimeoutError,)
    middleware: MiddlewareConfig = MiddlewareConfig(stop_processing=True)


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


def load_config(concurrent_requests: int | None = None, pending_requests: int | None = None) -> Config:
    "Load config from environment variables, falling back to defaults and optional CLI overrides."
    default_config = Config()
    default_retry = default_config.session.retry

    if concurrent_requests is None:
        concurrent_requests = env_parser.parse_int(
            "SCHEDULER_CONCURRENT_REQUESTS",
            default_config.scheduler.concurrent_requests,
        )

    if pending_requests is None:
        pending_requests = env_parser.parse_int(
            "SCHEDULER_PENDING_REQUESTS",
            default_config.scheduler.pending_requests,
        )

    if (raw_ssl_value := env_parser.parse_str("SESSION_SSL", default=None)) is not None:
        if raw_ssl_value.lower() not in {"true", "false"}:
            ssl_ctx = ssl_module.create_default_context()
            ssl_ctx.load_verify_locations(raw_ssl_value)
        else:
            ssl_ctx = env_parser.to_bool(raw_ssl_value)
    else:
        ssl_ctx = True

    if retry_exceptions_raw := env_parser.parse_list("SESSION_RETRY_EXCEPTIONS", default=None):
        retry_exceptions = tuple(_import_exception(item) for item in retry_exceptions_raw)
    else:
        retry_exceptions = default_retry.exceptions

    return Config(
        session=SessionConfig(
            timeout=env_parser.parse_float("SESSION_REQUEST_TIMEOUT", default_config.session.timeout),
            delay=env_parser.parse_float("SESSION_REQUEST_DELAY", default_config.session.delay),
            ssl=ssl_ctx,
            proxy=env_parser.parse_proxy("SESSION_PROXY", None),
            http_backend=env_parser.parse("SESSION_HTTP_BACKEND", HttpBackend, default_config.session.http_backend),
            retry=RequestRetryConfig(
                enabled=env_parser.parse_bool("SESSION_RETRY_ENABLED", default_retry.enabled),
                attempts=env_parser.parse_int("SESSION_RETRY_ATTEMPTS", default_retry.attempts),
                delay=env_parser.parse_float("SESSION_RETRY_DELAY", default_retry.delay),
                statuses=env_parser.parse_tuple("SESSION_RETRY_STATUSES", int, default_retry.statuses),
                exceptions=retry_exceptions,
                middleware=MiddlewareConfig(
                    priority=env_parser.parse_int(
                        "SESSION_RETRY_MIDDLEWARE_PRIORITY", default_retry.middleware.priority
                    ),
                    stop_processing=env_parser.parse_bool(
                        "SESSION_RETRY_MIDDLEWARE_STOP", default_retry.middleware.stop_processing
                    ),
                ),
            ),
        ),
        scheduler=SchedulerConfig(
            concurrent_requests=concurrent_requests,
            pending_requests=pending_requests,
            close_timeout=env_parser.parse_float("SCHEDULER_CLOSE_TIMEOUT", default_config.scheduler.close_timeout),
        ),
        execution=ExecutionConfig(
            timeout=env_parser.parse_float("EXECUTION_TIMEOUT", default_config.execution.timeout),
            shutdown_timeout=env_parser.parse_float(
                "EXECUTION_SHUTDOWN_TIMEOUT", default_config.execution.shutdown_timeout
            ),
            shutdown_check_interval=env_parser.parse_float(
                "EXECUTION_SHUTDOWN_CHECK_INTERVAL", default_config.execution.shutdown_check_interval
            ),
            log_level=env_parser.parse_log_level("EXECUTION_LOG_LEVEL", default_config.execution.log_level),
        ),
        pipeline=PipelineConfig(strict=env_parser.parse_bool("PIPELINE_STRICT", default_config.pipeline.strict)),
    )


def _import_exception(path: str) -> type[BaseException]:
    module_name, _, attr = path.rpartition(".")
    if not module_name:
        raise ValueError(f"Expected fully qualified exception path, got {path!r}")
    module = importlib.import_module(module_name)
    exc = getattr(module, attr)
    if not isinstance(exc, type) or not issubclass(exc, BaseException):
        raise ValueError(f"{path!r} is not an exception type")
    return exc
