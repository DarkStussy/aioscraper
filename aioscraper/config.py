import logging
from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class RequestConfig:
    """
    Configuration for HTTP requests.

    Attributes:
        timeout (int): Request timeout in seconds. Default is 60.
        delay (float): Delay between requests in seconds. Default is 0.0.
        ssl (bool): Whether to use SSL for requests. Default is True.
    """

    timeout: int = 60
    delay: float = 0.0
    ssl: bool = True


@dataclass(slots=True, frozen=True)
class SessionConfig:
    """
    Configuration for HTTP session.

    Attributes:
        request (RequestConfig): Configuration for individual requests within the session.
    """

    request: RequestConfig = RequestConfig()


@dataclass(slots=True, frozen=True)
class SchedulerConfig:
    """
    Configuration for request scheduler.

    Attributes:
        concurrent_requests (int): Maximum number of concurrent requests. Default is 64.
        pending_requests (int): Number of pending requests to maintain. Default is 1.
        close_timeout (float | None): Timeout for closing scheduler in seconds. Default is 0.1.
    """

    concurrent_requests: int = 64
    pending_requests: int = 1
    close_timeout: float | None = 0.1


@dataclass(slots=True, frozen=True)
class ExecutionConfig:
    """
    Configuration for execution.

    Attributes:
        timeout (float | None): Overall execution timeout in seconds. Default is None (no timeout).
        shutdown_timeout (float): Timeout for graceful shutdown in seconds. Default is 0.1.
        shutdown_check_interval (float): Interval between shutdown checks in seconds. Default is 0.1.
        log_level (int): Logging level. Default is logging.ERROR.
    """

    timeout: float | None = None
    shutdown_timeout: float = 0.1
    shutdown_check_interval: float = 0.1
    log_level: int = logging.ERROR


@dataclass(slots=True, frozen=True)
class Config:
    """
    Main configuration class that combines all configuration components.

    Attributes:
        session (SessionConfig): HTTP session configuration.
        scheduler (SchedulerConfig): Request scheduler configuration.
        execution (ExecutionConfig): Script execution configuration.
    """

    session: SessionConfig = SessionConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
    execution: ExecutionConfig = ExecutionConfig()
