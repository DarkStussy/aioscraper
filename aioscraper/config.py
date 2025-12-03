import logging
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class RequestConfig:
    """
    Configuration for HTTP requests.

    Args:
        timeout (int): Request timeout in seconds
        delay (float): Delay between requests in seconds
        ssl (bool): Whether to use SSL for requests
    """

    timeout: int = 60
    delay: float = 0.0
    ssl: bool = True


@dataclass(slots=True, frozen=True)
class SessionConfig:
    "Configuration for HTTP session."

    request: RequestConfig = RequestConfig()


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
class Config:
    "Main configuration class that combines all configuration components."

    session: SessionConfig = SessionConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
    execution: ExecutionConfig = ExecutionConfig()
