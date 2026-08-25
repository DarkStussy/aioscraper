import logging
import random
import ssl as ssl_module
from dataclasses import dataclass
from enum import StrEnum, auto
from http import HTTPMethod
from typing import Callable, Hashable

from aioscraper.exceptions import ConnectionFailed, TransportTimeout
from aioscraper.types import Request
from aioscraper.types.session import DEFAULT_MAX_ERROR_BODY_SIZE, DEFAULT_MAX_RESPONSE_BODY_SIZE

from .field_validators import CustomValidator, ProxyValidator, RangeValidator
from .model_validator import field, validate


@dataclass(slots=True, frozen=True)
@validate
class AdaptiveRateLimitConfig:
    """Lets each rate limit group find its own pace instead of holding the configured one.

    The interval is multiplied on server pushback and stepped back down after a run of successes,
    per group. Setting this leaves ``default_interval`` as the starting point.

    Args:
        min_interval (float): Floor for the interval, in seconds.
        max_interval (float): Ceiling for the interval, in seconds; a ``Retry-After`` is clamped
            to it too.
        increase_factor (float): The interval is multiplied by this on a failure.
        decrease_step (float): Seconds taken off after a run of successes.
        success_threshold (int): How many successes in a row it takes to step down.
        ewma_alpha (float): Weight of the newest latency sample, 0 to 1; higher follows the recent
            requests more closely.
        respect_retry_after (bool): Let a ``Retry-After`` on a 429 or 503 set the interval outright.
        inherit_retry_triggers (bool): Also treat what :class:`RequestRetryConfig` retries as
            pushback.
        custom_trigger_statuses (tuple[int, ...]): Statuses that count as pushback on top of the
            built-in ones.
        custom_trigger_exceptions (tuple[type[BaseException], ...]): Exceptions that count as
            pushback on top of the built-in ones.
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
    """How requests are spaced out, per group of related targets.

    Args:
        enabled (bool): Group requests and pace each group separately. Off by default, in which
            case ``default_interval`` still applies, but to the whole run rather than per group.
        group_by (Callable[[Request], tuple[Hashable, float]] | None): Maps a request to its group
            key and that group's interval. Grouping is by hostname when this is ``None``.
        default_interval (float): Seconds between requests under the built-in hostname grouping.
            A ``group_by`` of your own returns the interval itself, so this is not consulted; with
            ``enabled`` off it becomes a flat delay between all requests.
        cleanup_timeout (float): Idle time after which a group is dropped.
        adaptive (AdaptiveRateLimitConfig | None): Adjust the intervals from how the requests
            actually go; ``None`` keeps them fixed.
    """

    enabled: bool = False
    group_by: Callable[[Request], tuple[Hashable, float]] | None = field(default=None, skip_validation=True)
    default_interval: float = field(default=0.0, validator=RangeValidator(min_value=0.0))
    cleanup_timeout: float = field(default=60.0, validator=RangeValidator(min_value=0.1))
    adaptive: AdaptiveRateLimitConfig | None = None


class BackoffStrategy(StrEnum):
    """How the delay before a retry grows with the attempt number.

    Attributes:
        CONSTANT: Always ``base_delay``.
        LINEAR: ``base_delay * attempt``, uncapped.
        EXPONENTIAL: ``base_delay * 2 ** attempt``, capped at ``max_delay``.
        EXPONENTIAL_JITTER: The same, with the second half of each delay randomized, so retries of
            a batch that failed together do not come back together.
    """

    CONSTANT = auto()
    LINEAR = auto()
    EXPONENTIAL = auto()
    EXPONENTIAL_JITTER = auto()


@dataclass(slots=True, frozen=True)
@validate
class RequestRetryConfig:
    """Retry behavior applied by the dispatcher.

    Args:
        enabled (bool): Toggle retries on or off. On by default, which costs a failing endpoint
            ``attempts`` extra requests per URL.
        attempts (int): How many extra sends a request gets, on top of the first one.
        backoff (BackoffStrategy): How the delay grows from one attempt to the next.
        base_delay (float): Delay the backoff is computed from, in seconds.
        max_delay (float): Cap on a computed delay, in seconds. ``LINEAR`` ignores it.
        max_retry_after (float): Cap in seconds on a delay the server asked for through
            ``Retry-After``; a longer one is clamped to it. Bounds how long a run can be parked.
        statuses (tuple[int, ...]): HTTP status codes that should trigger a retry.
        exceptions (tuple[type[BaseException], ...]): Exception types that should trigger a retry.
            Defaults to the transient transport failures, which every backend raises alike;
            :class:`~aioscraper.exceptions.TLSError` is left out.
        methods (tuple[str, ...]): HTTP methods eligible for a retry, case-insensitive.
            ``Request.retryable`` overrides it per request.
        should_retry (Callable[[Request, Exception, int], bool | None] | None): Decides a failure the
            ``statuses``/``exceptions`` match cannot express; ``None`` defers to that match, and the
            method check applies first.
    """

    enabled: bool = True
    attempts: int = field(default=3, validator=RangeValidator(min_value=1))
    backoff: BackoffStrategy = BackoffStrategy.EXPONENTIAL_JITTER
    base_delay: float = field(default=0.5, validator=RangeValidator(min_value=0.001))
    max_delay: float = field(default=30.0, validator=RangeValidator(min_value=0.001))
    max_retry_after: float = field(default=600.0, validator=RangeValidator(min_value=0.001))
    statuses: tuple[int, ...] = (500, 502, 503, 504, 522, 524, 408, 429)
    exceptions: tuple[type[BaseException], ...] = (TransportTimeout, ConnectionFailed)
    methods: tuple[str, ...] = field(
        default=(HTTPMethod.GET, HTTPMethod.HEAD, HTTPMethod.OPTIONS, HTTPMethod.TRACE),
        validator=CustomValidator(lambda methods: tuple(method.upper() for method in methods)),
    )
    should_retry: Callable[[Request, Exception, int], bool | None] | None = field(
        default=None,
        skip_validation=True,
    )

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
    HTTPX2 = "httpx2"


@dataclass(slots=True, frozen=True)
@validate
class SessionConfig:
    """HTTP session settings shared by every request.

    Args:
        timeout (float): Budget in seconds for the whole response - send, headers and body - unless
            the request carries its own; enforced by the framework on every backend
        ssl (ssl.SSLContext | bool): SSL handling; bool toggles verification, SSLContext can carry custom CAs
        proxy (str | dict[str, str | None] | None): Default proxy passed to the HTTP client
        http_backend (HttpBackend | None): Force ``aiohttp``/``httpx``/``httpx2``; ``None`` lets the factory auto-detect
        max_response_body_size (int | None): Cap on a response body in bytes, 32 MiB by default;
            ``None`` disables it. Bounds memory at this value times ``scheduler.concurrent_requests``
        max_error_body_size (int): Bytes of a failed response read into the ``HTTPException`` message
        retry (RequestRetryConfig): Controls built-in retry behavior
        rate_limit (RateLimitConfig): Controls built-in rate limiting behavior
        buffer_body (bool): Whether to read a response body before the callback runs;
            ``Request.buffer_body`` overrides it per request
    """

    timeout: float = field(default=60.0, validator=RangeValidator(min_value=0.001))
    ssl: ssl_module.SSLContext | bool = True
    proxy: str | dict[str, str | None] | None = field(default=None, validator=ProxyValidator({"http", "https"}))
    http_backend: HttpBackend | None = None
    max_response_body_size: int | None = field(
        default=DEFAULT_MAX_RESPONSE_BODY_SIZE,
        validator=RangeValidator(min_value=1),
    )
    max_error_body_size: int = field(
        default=DEFAULT_MAX_ERROR_BODY_SIZE,
        validator=RangeValidator(min_value=0),
    )
    retry: RequestRetryConfig = RequestRetryConfig()
    rate_limit: RateLimitConfig = RateLimitConfig()
    buffer_body: bool = False


@dataclass(slots=True, frozen=True)
@validate
class SchedulerConfig:
    """Limits on the ``aiojobs`` scheduler that runs the requests.

    Args:
        concurrent_requests (int): Requests allowed in flight at once, across every rate limit
            group.
        pending_requests (int): How many attempts may sit inside the scheduler waiting for a free
            slot.
        close_timeout (float | None): Grace period a job gets when the scheduler is closed.
        ready_queue_max_size (int): Throttles the entrypoint at this many accepted but
            unscheduled requests (0 for unlimited); sends from inside a job are not blocked.
    """

    concurrent_requests: int = field(default=64, validator=RangeValidator(min_value=1))
    pending_requests: int = field(default=1, validator=RangeValidator(min_value=1))
    close_timeout: float | None = field(default=0.1, validator=RangeValidator(min_value=0.01))
    ready_queue_max_size: int = field(default=0, validator=RangeValidator(min_value=0))


DEFAULT_MAX_RETAINED_ERRORS = 100


class ErrorPolicy(StrEnum):
    """What an unhandled error means for the exit code. Read by the CLI, and by nothing else.

    Attributes:
        LOG: Log it and exit ``0``.
        FAIL: Log it and exit ``1``.
    """

    LOG = auto()
    FAIL = auto()


@dataclass(slots=True, frozen=True)
@validate
class ExecutionConfig:
    """How long the run may take and how it is stopped.

    Args:
        timeout (float | None): Budget for the whole run, in seconds; ``None`` gives it no
            deadline. Once it expires the run is cut short and ``RunResult.timed_out`` is set.
        shutdown_timeout (float): How long in-flight work gets to finish after SIGINT/SIGTERM or
            an expired ``timeout``, before it is canceled.
        shutdown_check_interval (float): How long the queue listener may block before rechecking
            whether the run is over. Bounds how late a shutdown is noticed.
        on_error (ErrorPolicy): Whether unhandled errors make the CLI exit non-zero.
        log_level (int): Level the timeout message is logged at.
        max_retained_errors (int): How many exceptions ``RunResult.errors`` keeps; the counts stay
            exact either way. ``0`` keeps none, which frees the tracebacks a failing run holds.
    """

    timeout: float | None = field(default=None, validator=RangeValidator(min_value=0.01))
    shutdown_timeout: float = field(default=0.1, validator=RangeValidator(min_value=0.001))
    shutdown_check_interval: float = field(default=0.1, validator=RangeValidator(min_value=0.01))
    on_error: ErrorPolicy = ErrorPolicy.FAIL
    log_level: int = logging.ERROR
    max_retained_errors: int = field(
        default=DEFAULT_MAX_RETAINED_ERRORS,
        validator=RangeValidator(min_value=0),
    )


@dataclass(slots=True, frozen=True)
@validate
class PipelineConfig:
    """
    Args:
        strict (bool): Raise :class:`PipelineException` for an item type nothing is registered
            for. Turning it off logs a warning and returns the item untouched.
    """

    strict: bool = True


@dataclass(slots=True, frozen=True)
@validate
class Config:
    "Everything a run is configured with. Build one directly, or from the environment with :func:`load_config`."

    session: SessionConfig = SessionConfig()
    scheduler: SchedulerConfig = SchedulerConfig()
    execution: ExecutionConfig = ExecutionConfig()
    pipeline: PipelineConfig = PipelineConfig()
