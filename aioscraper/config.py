import logging
from dataclasses import dataclass

from . import env_parser


@dataclass(slots=True, frozen=True)
class SessionConfig:
    """Configuration for session.

    Args:
        timeout (int): Request timeout in seconds
        delay (float): Delay between requests in seconds
        ssl (bool): Whether to use SSL for requests
    """

    timeout: float = 60.0
    delay: float = 0.0
    ssl: bool = True


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
    default_config = Config()

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

    return Config(
        session=SessionConfig(
            timeout=env_parser.parse_float("SESSION_REQUEST_TIMEOUT", default_config.session.timeout),
            delay=env_parser.parse_float("SESSION_REQUEST_DELAY", default_config.session.delay),
            ssl=env_parser.parse_bool("SESSION_SSL", default_config.session.ssl),
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
