import ssl as ssl_module

from .models import (
    Config,
    MiddlewareConfig,
    RateLimitConfig,
    RequestRetryConfig,
    SessionConfig,
    SchedulerConfig,
    ExecutionConfig,
    PipelineConfig,
    HttpBackend,
    BackoffStrategy,
)
from .._helpers.module import import_exception
from .. import env_parser


def load_config(concurrent_requests: int | None = None, pending_requests: int | None = None) -> Config:
    """Load configuration from environment variables with optional CLI overrides.

    Reads configuration from environment variables prefixed with SESSION_, SCHEDULER_,
    EXECUTION_, and PIPELINE_. When parameters are None, values are read from
    corresponding environment variables. Defaults are used when env vars are not set.

    Args:
        concurrent_requests (int | None): Override for SCHEDULER_CONCURRENT_REQUESTS.
            If None, reads from environment or uses default (64).
        pending_requests (int | None): Override for SCHEDULER_PENDING_REQUESTS.
            If None, reads from environment or uses default (1).

    Returns:
        Config: Complete configuration object with all settings resolved.
    """
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
        retry_exceptions = tuple(import_exception(item) for item in retry_exceptions_raw)
    else:
        retry_exceptions = default_retry.exceptions

    return Config(
        session=SessionConfig(
            timeout=env_parser.parse_float("SESSION_REQUEST_TIMEOUT", default_config.session.timeout),
            ssl=ssl_ctx,
            proxy=env_parser.parse_proxy("SESSION_PROXY", None),
            http_backend=env_parser.parse("SESSION_HTTP_BACKEND", HttpBackend, default_config.session.http_backend),
            retry=RequestRetryConfig(
                enabled=env_parser.parse_bool("SESSION_RETRY_ENABLED", default_retry.enabled),
                attempts=env_parser.parse_int("SESSION_RETRY_ATTEMPTS", default_retry.attempts),
                backoff=env_parser.parse("SESSION_RETRY_BACKOFF", BackoffStrategy, default_retry.backoff),
                base_delay=env_parser.parse_float("SESSION_RETRY_BASE_DELAY", default_retry.base_delay),
                max_delay=env_parser.parse_float("SESSION_RETRY_MAX_DELAY", default_retry.max_delay),
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
            rate_limit=RateLimitConfig(
                enabled=env_parser.parse_bool("SESSION_RATE_LIMIT_ENABLED", default_config.session.rate_limit.enabled),
                default_interval=env_parser.parse_float(
                    "SESSION_RATE_LIMIT_INTERVAL", default_config.session.rate_limit.default_interval
                ),
                cleanup_timeout=env_parser.parse_float(
                    "SESSION_RATE_LIMIT_CLEANUP_TIMEOUT", default_config.session.rate_limit.cleanup_timeout
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
