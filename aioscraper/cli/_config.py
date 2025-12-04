from .. import env_parser
from ..config import Config, ExecutionConfig, SchedulerConfig, SessionConfig


def build_config(concurrent_requests: int | None, pending_requests: int | None) -> Config:
    default_config = Config()

    concurrent_requests = concurrent_requests or env_parser.parse_int(
        "SCHEDULER_CONCURRENT_REQUESTS",
        default_config.scheduler.concurrent_requests,
    )
    pending_requests = pending_requests or env_parser.parse_int(
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
    )
