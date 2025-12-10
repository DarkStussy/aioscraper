import ssl as ssl_module

from aioscraper._helpers.module import import_exception

from . import env
from .models import (
    AdaptiveRateLimitConfig,
    Config,
    ExecutionConfig,
    MiddlewareConfig,
    PipelineConfig,
    RateLimitConfig,
    RequestRetryConfig,
    SchedulerConfig,
    SessionConfig,
)


def load_config() -> Config:
    """Load configuration from environment variables.

    Reads configuration from environment variables prefixed with `SESSION`, `SCHEDULER`,
    `EXECUTION`, and `PIPELINE`. When parameters are None, values are read from
    corresponding environment variables. Defaults are used when env vars are not set.

    Returns:
        Config: Complete configuration object with all settings resolved.
    """
    default_config = Config()
    default_retry = default_config.session.retry
    default_adaptive_rate_limit = AdaptiveRateLimitConfig()

    if (raw_ssl_value := env.parse("SESSION_SSL", None)) is not None:
        if raw_ssl_value.lower() not in {"true", "false"}:
            ssl_ctx = ssl_module.create_default_context()
            ssl_ctx.load_verify_locations(raw_ssl_value)
        else:
            ssl_ctx = env.to_bool(raw_ssl_value)
    else:
        ssl_ctx = True

    if retry_exceptions_raw := env.parse_list("SESSION_RETRY_EXCEPTIONS", None):
        retry_exceptions = tuple(import_exception(item) for item in retry_exceptions_raw)
    else:
        retry_exceptions = default_retry.exceptions

    return Config(
        session=SessionConfig(
            timeout=env.parse("SESSION_REQUEST_TIMEOUT", default_config.session.timeout),
            ssl=ssl_ctx,
            proxy=env.parse_proxy("SESSION_PROXY", None),
            http_backend=env.parse("SESSION_HTTP_BACKEND", default_config.session.http_backend),
            retry=RequestRetryConfig(
                enabled=env.parse("SESSION_RETRY_ENABLED", default_retry.enabled),
                attempts=env.parse("SESSION_RETRY_ATTEMPTS", default_retry.attempts),
                backoff=env.parse("SESSION_RETRY_BACKOFF", default_retry.backoff),
                base_delay=env.parse("SESSION_RETRY_BASE_DELAY", default_retry.base_delay),
                max_delay=env.parse("SESSION_RETRY_MAX_DELAY", default_retry.max_delay),
                statuses=env.parse_tuple("SESSION_RETRY_STATUSES", default_retry.statuses, cast=int),
                exceptions=retry_exceptions,
                middleware=MiddlewareConfig(
                    priority=env.parse("SESSION_RETRY_MIDDLEWARE_PRIORITY", default_retry.middleware.priority),
                    stop_processing=env.parse(
                        "SESSION_RETRY_MIDDLEWARE_STOP",
                        default_retry.middleware.stop_processing,
                    ),
                ),
            ),
            rate_limit=RateLimitConfig(
                enabled=env.parse("SESSION_RATE_LIMIT_ENABLED", default_config.session.rate_limit.enabled),
                default_interval=env.parse(
                    "SESSION_RATE_LIMIT_INTERVAL",
                    default_config.session.rate_limit.default_interval,
                ),
                cleanup_timeout=env.parse(
                    "SESSION_RATE_LIMIT_CLEANUP_TIMEOUT",
                    default_config.session.rate_limit.cleanup_timeout,
                ),
                adaptive=(
                    AdaptiveRateLimitConfig(
                        min_interval=env.parse(
                            "SESSION_RATE_LIMIT_ADAPTIVE_MIN_INTERVAL",
                            default_adaptive_rate_limit.min_interval,
                        ),
                        max_interval=env.parse(
                            "SESSION_RATE_LIMIT_ADAPTIVE_MAX_INTERVAL",
                            default_adaptive_rate_limit.max_interval,
                        ),
                        increase_factor=env.parse(
                            "SESSION_RATE_LIMIT_ADAPTIVE_INCREASE_FACTOR",
                            default_adaptive_rate_limit.increase_factor,
                        ),
                        decrease_step=env.parse(
                            "SESSION_RATE_LIMIT_ADAPTIVE_DECREASE_STEP",
                            default_adaptive_rate_limit.decrease_step,
                        ),
                        success_threshold=env.parse(
                            "SESSION_RATE_LIMIT_ADAPTIVE_SUCCESS_THRESHOLD",
                            default_adaptive_rate_limit.success_threshold,
                        ),
                        ewma_alpha=env.parse(
                            "SESSION_RATE_LIMIT_ADAPTIVE_EWMA_ALPHA",
                            default_adaptive_rate_limit.ewma_alpha,
                        ),
                        respect_retry_after=env.parse(
                            "SESSION_RATE_LIMIT_ADAPTIVE_RESPECT_RETRY_AFTER",
                            default_adaptive_rate_limit.respect_retry_after,
                        ),
                        inherit_retry_triggers=env.parse(
                            "SESSION_RATE_LIMIT_ADAPTIVE_INHERIT_RETRY_TRIGGERS",
                            default_adaptive_rate_limit.inherit_retry_triggers,
                        ),
                    )
                    if env.parse("SESSION_RATE_LIMIT_ADAPTIVE_ENABLED", default=False)
                    else None
                ),
            ),
        ),
        scheduler=SchedulerConfig(
            concurrent_requests=env.parse(
                "SCHEDULER_CONCURRENT_REQUESTS",
                default_config.scheduler.concurrent_requests,
            ),
            pending_requests=env.parse(
                "SCHEDULER_PENDING_REQUESTS",
                default_config.scheduler.pending_requests,
            ),
            close_timeout=env.parse("SCHEDULER_CLOSE_TIMEOUT", default_config.scheduler.close_timeout),
        ),
        execution=ExecutionConfig(
            timeout=env.parse("EXECUTION_TIMEOUT", default_config.execution.timeout),
            shutdown_timeout=env.parse("EXECUTION_SHUTDOWN_TIMEOUT", default_config.execution.shutdown_timeout),
            shutdown_check_interval=env.parse(
                "EXECUTION_SHUTDOWN_CHECK_INTERVAL",
                default_config.execution.shutdown_check_interval,
            ),
            log_level=env.parse_log_level("EXECUTION_LOG_LEVEL", default_config.execution.log_level),
        ),
        pipeline=PipelineConfig(strict=env.parse("PIPELINE_STRICT", default_config.pipeline.strict)),
    )
