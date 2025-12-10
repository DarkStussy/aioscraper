import asyncio
import logging
import sys
from contextlib import suppress
from dataclasses import dataclass
from time import monotonic
from typing import Any, Awaitable, Callable, Hashable, Self

from yarl import URL

from aioscraper.config import RateLimitConfig, RequestRetryConfig
from aioscraper.types.session import PRequest, Request

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AdaptiveMetrics:
    """Tracks metrics for adaptive rate limiting using EWMA + AIMD.

    Attributes:
        ewma_latency (float): Exponentially weighted moving average of request latency.
        ewma_alpha (float): Smoothing factor for EWMA (0 < alpha <= 1).
        success_count (int): Consecutive successful requests since last failure.
        failure_count (int): Consecutive failures since last success.
        last_outcome_time (float | None): Timestamp of last completed request.
        last_outcome_success (bool | None): Whether last request was successful.
        total_requests (int): Total number of completed requests in this group.
    """

    ewma_latency: float = 0.0
    ewma_alpha: float = 0.3
    success_count: int = 0
    failure_count: int = 0
    last_outcome_time: float | None = None
    last_outcome_success: bool = True
    total_requests: int = 0

    def update_latency(self, latency: float):
        """Update EWMA latency with new measurement."""
        if self.total_requests == 0:
            self.ewma_latency = latency
        else:
            self.ewma_latency = (self.ewma_alpha * latency) + ((1 - self.ewma_alpha) * self.ewma_latency)

    def record_success(self, latency: float):
        """Record a successful request outcome."""
        self.update_latency(latency)
        self.success_count += 1
        self.failure_count = 0
        self.last_outcome_success = True
        self.last_outcome_time = monotonic()
        self.total_requests += 1

    def record_failure(self, latency: float | None = None):
        """Record a failed request outcome (timeout, error status, etc)."""
        if latency is not None:
            self.update_latency(latency)

        self.failure_count += 1
        self.success_count = 0
        self.last_outcome_success = False
        self.last_outcome_time = monotonic()
        self.total_requests += 1


@dataclass(slots=True)
class RequestOutcome:
    """Captures the result of a request execution.

    Attributes:
        group_key (Hashable): The RequestGroup key this outcome belongs to.
        latency (float): Request latency in seconds (start to finish).
        retry_after (float | None): Value from Retry-After header if present.
        status_code (int | None): HTTP status code if applicable.
        exception_type (type[BaseException] | None): Type of exception if one occurred.
    """

    group_key: Hashable
    latency: float
    retry_after: float | None = None
    status_code: int | None = None
    exception_type: type[BaseException] | None = None


class AdaptiveStrategy:
    """EWMA + AIMD adaptive rate limiting strategy.

    Fast multiplicative increase on overload (server pushback).
    Slow additive decrease on sustained success (probing for capacity).

    Args:
        enabled (bool): Enable adaptive rate limiting.
        min_interval (float): Minimum allowed interval (seconds).
        max_interval (float): Maximum allowed interval (seconds).
        increase_factor (float): Multiplicative factor for interval increase on failure.
        decrease_step (float): Additive step for interval decrease on success.
        success_threshold (int): Number of consecutive successes before decreasing interval.
        ewma_alpha (float): Smoothing factor for latency EWMA (0 < alpha <= 1).
        trigger_statuses (tuple[int, ...]): HTTP statuses that trigger adaptive slowdown.
        trigger_exceptions (tuple[type[BaseException], ...]): Exception types that trigger adaptive slowdown.
        respect_retry_after (bool): Whether to use Retry-After header as override.
    """

    def __init__(
        self,
        *,
        min_interval: float = 0.001,
        max_interval: float = 5.0,
        increase_factor: float = 2.0,
        decrease_step: float = 0.01,
        success_threshold: int = 5,
        ewma_alpha: float = 0.3,
        trigger_statuses: tuple[int, ...] = (429, 500, 502, 503, 504, 522, 524, 408),
        trigger_exceptions: tuple[type[BaseException], ...] = (asyncio.TimeoutError,),
        respect_retry_after: bool = True,
    ):
        self.min_interval = min_interval
        self.max_interval = max_interval
        self.increase_factor = increase_factor
        self.decrease_step = decrease_step
        self.success_threshold = success_threshold
        self.ewma_alpha = ewma_alpha
        self.trigger_statuses = set(trigger_statuses)
        self.trigger_exceptions = trigger_exceptions
        self.respect_retry_after = respect_retry_after
        self._metrics: dict[Hashable, AdaptiveMetrics] = {}

    def get_or_create_metrics(self, group_key: Hashable) -> AdaptiveMetrics:
        """Get or create metrics for a group."""
        if group_key not in self._metrics:
            self._metrics[group_key] = AdaptiveMetrics(ewma_alpha=self.ewma_alpha)

        return self._metrics[group_key]

    def calculate_interval(self, group_key: Hashable, current_interval: float, outcome: RequestOutcome) -> float:
        """Calculate new interval based on request outcome.

        Algorithm:
        - On failure: interval = min(max_interval, interval * increase_factor)
        - On success: if success_count >= threshold: interval = max(min_interval, interval - decrease_step)
        - Retry-After override: Use header value if present and enabled

        Returns:
            New interval in seconds.
        """
        metrics = self.get_or_create_metrics(group_key)

        success = not self._is_adaptive_failure(outcome.status_code, outcome.exception_type)

        if success:
            metrics.record_success(outcome.latency)
        else:
            metrics.record_failure(outcome.latency)

        # Priority 1: Retry-After override takes precedence
        if self.respect_retry_after and outcome.retry_after is not None and not success:
            new_interval = min(self.max_interval, outcome.retry_after)
            logger.info(
                "Adaptive rate limit: Retry-After header for group %r, setting interval to %.4f "
                "(status=%s, latency=%.4f)",
                group_key,
                new_interval,
                outcome.status_code,
                outcome.latency,
            )
            return new_interval

        # Priority 2: Apply AIMD
        if not success:
            # Multiplicative increase on failure
            new_interval = current_interval * self.increase_factor
            logger.info(
                "Adaptive rate limit: failure for group %r, increasing interval %.4f -> %.4f "
                "(status=%s, latency=%.4f, failure_count=%d)",
                group_key,
                current_interval,
                new_interval,
                outcome.status_code or "exception",
                outcome.latency,
                metrics.failure_count,
            )
        elif metrics.success_count >= self.success_threshold:
            # Additive decrease after sustained success
            new_interval = current_interval - self.decrease_step
            logger.debug(
                "Adaptive rate limit: sustained success for group %r, decreasing interval %.4f -> %.4f "
                "(latency=%.4f, success_count=%d)",
                group_key,
                current_interval,
                new_interval,
                outcome.latency,
                metrics.success_count,
            )
        else:
            # Not enough successes yet, maintain current interval
            new_interval = current_interval

        return max(self.min_interval, min(self.max_interval, new_interval))

    def reset_metrics(self, group_key: Hashable):
        """Reset metrics for a group (e.g., on cleanup)."""
        self._metrics.pop(group_key, None)

    def _is_adaptive_failure(self, status_code: int | None, exception_type: type[BaseException] | None) -> bool:
        """Check if status/exception should trigger adaptive slowdown."""
        if status_code and status_code in self.trigger_statuses:
            return True

        if exception_type and any(issubclass(exception_type, exc_type) for exc_type in self.trigger_exceptions):
            return True

        return False


def default_group_by_factory(default_interval: float) -> Callable[[Request], tuple[Hashable, float]]:
    "Creates a default grouping function that groups requests by hostname."

    def _group_by(request: Request) -> tuple[Hashable, float]:
        return URL(request.url).host or "unknown", default_interval

    return _group_by


class RequestGroup:
    """Manages a group of requests that share the same rate limit interval.

    Each group processes requests sequentially with a configured delay between them.
    Groups automatically clean up after a period of inactivity.

    Args:
        key (Hashable): Unique identifier for this request group.
        interval (float): Delay in seconds between processing requests in this group.
        cleanup_timeout (float): Timeout in seconds before cleaning up an idle group.
        schedule (Callable[[PRequest], Awaitable[None]]): Callback function to schedule request execution.
        on_finished (Callable[[Hashable, RequestGroup], None]):
            Callback invoked when the group finishes or becomes idle.
    """

    def __init__(
        self,
        key: Hashable,
        interval: float,
        cleanup_timeout: float,
        schedule: Callable[[PRequest], Awaitable[None]],
        on_finished: Callable[[Hashable, "RequestGroup"], None],
    ):
        self._key = key
        self._interval = interval
        self._cleanup_timeout = max(cleanup_timeout, self._interval * 2)
        self._schedule = schedule
        self._on_finished = on_finished
        self._queue: asyncio.PriorityQueue[PRequest] = asyncio.PriorityQueue()
        self._task: asyncio.Task[None] | None = None

    @property
    def key(self) -> Hashable:
        return self._key

    @property
    def active(self) -> bool:
        "Check if the group has pending requests in its queue."
        return not self._queue.empty()

    @property
    def interval(self) -> float:
        "Get the current interval for this group."
        return self._interval

    @property
    def worker_alive(self) -> bool:
        if self._task is None:
            return False

        return not self._task.done() and not self._task.cancelled()

    def set_intervals(self, interval: float, cleanup_timeout: float):
        "Update group interval and cleanup timeout."
        self._interval = interval
        self._cleanup_timeout = cleanup_timeout

    async def put(self, pr: PRequest):
        "Add a request to this group's processing queue."
        await self._queue.put(pr)

    def start_listening(self):
        if self._task is not None:
            return

        self._task = asyncio.create_task(self._listen_queue())
        self._task.add_done_callback(self._on_task_done_factory())

    async def close(self):
        "Cancel the worker task and wait for graceful shutdown."
        if self._task is None:
            return

        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task

    async def _listen_queue(self):
        while True:
            try:
                # Wait for next request with timeout. If no requests arrive within
                # cleanup_timeout, the group is considered idle and will be cleaned up.
                pr = await asyncio.wait_for(self._queue.get(), timeout=self._cleanup_timeout)
            except asyncio.TimeoutError:
                # Race condition: item may have been added while timeout was firing
                if not self._queue.empty():
                    continue

                # Group is idle - trigger cleanup callback and exit worker loop
                self._on_finished(self._key, self)
                break

            if pr.request.url == "stub":
                break

            try:
                await asyncio.shield(self._schedule(pr))
            except Exception:
                logger.exception("Rate limiter scheduler failed for %r", self._key)

            await asyncio.sleep(self._interval)

    def _on_task_done_factory(self) -> Callable[[asyncio.Task[None]], None]:
        def _on_task_done(task: asyncio.Task[None]):
            if task.cancelled():
                logger.debug("Rate limiter group %r cancelled", self._key)
                return

            with suppress(asyncio.CancelledError):
                exc = task.exception()

            if exc is not None:
                logger.error("Rate limiter group %r crashed: %s", self._key, exc, exc_info=exc)

            self._on_finished(self._key, self)

        return _on_task_done


class RateLimitManager:
    """Manages rate limiting for requests using group-based throttling.

    Requests are grouped by a configurable key (default: hostname) and processed
    with a specified interval between requests in each group. Groups are created
    dynamically and cleaned up automatically after inactivity.

    Args:
        config (RateLimitConfig): Rate limiting configuration including grouping strategy and intervals.
        retry_config (RequestRetryConfig): Retry configuration for inheriting trigger conditions.
        schedule (Callable[[PRequest], Awaitable[Any]]): Callback function to schedule request execution.
    """

    def __init__(
        self,
        config: RateLimitConfig,
        retry_config: RequestRetryConfig,
        schedule: Callable[[PRequest], Awaitable[Any]],
    ):
        self._schedule = schedule
        self._group_by = config.group_by or default_group_by_factory(config.default_interval)
        self._default_interval = config.default_interval
        self._cleanup_timeout = config.cleanup_timeout
        self._groups: dict[Hashable, RequestGroup] = {}
        self._enabled = config.enabled
        self._stopped = False

        self._adaptive_strategy: AdaptiveStrategy | None = None
        if config.enabled and config.adaptive:
            trigger_statuses = config.adaptive.custom_trigger_statuses
            trigger_exceptions = config.adaptive.custom_trigger_exceptions

            # Merge retry triggers if configured
            if config.adaptive.inherit_retry_triggers:
                trigger_statuses = tuple(set(trigger_statuses) | set(retry_config.statuses))
                trigger_exceptions = tuple(set(trigger_exceptions) | set(retry_config.exceptions))

            self._adaptive_strategy = AdaptiveStrategy(
                min_interval=config.adaptive.min_interval,
                max_interval=config.adaptive.max_interval,
                increase_factor=config.adaptive.increase_factor,
                decrease_step=config.adaptive.decrease_step,
                success_threshold=config.adaptive.success_threshold,
                ewma_alpha=config.adaptive.ewma_alpha,
                trigger_statuses=trigger_statuses,
                trigger_exceptions=trigger_exceptions,
                respect_retry_after=config.adaptive.respect_retry_after,
            )

        if config.enabled:
            self._handle = self._handle_with_group
            logger.info(
                "Rate limiting enabled: grouping=%s, default_interval=%0.10g, cleanup_timeout=%0.10g",
                "custom" if config.group_by else "by hostname",
                self._default_interval,
                self._cleanup_timeout,
            )
        else:
            self._handle = self._handle_without_group
            if self._default_interval > 0:
                logger.info(
                    "Rate limiting disabled (no grouping), but default_interval=%0.10g will be applied",
                    self._default_interval,
                )

        if config.adaptive and self._adaptive_strategy:
            logger.info(
                "Adaptive rate limiting enabled: min_interval=%.3f, max_interval=%.3f, "
                "increase_factor=%.2f, decrease_step=%.3f, success_threshold=%d, ewma_alpha=%.2f",
                config.adaptive.min_interval,
                config.adaptive.max_interval,
                config.adaptive.increase_factor,
                config.adaptive.decrease_step,
                config.adaptive.success_threshold,
                config.adaptive.ewma_alpha,
            )
            logger.info(
                "Adaptive rate limiting triggers (inherit_retry_triggers=%s): statuses=%s; exceptions=%s",
                config.adaptive.inherit_retry_triggers,
                ",".join(map(str, sorted(self._adaptive_strategy.trigger_statuses))),
                ",".join(exc.__module__ + "." + exc.__qualname__ for exc in self._adaptive_strategy.trigger_exceptions),
            )

    @property
    def adaptive_strategy(self) -> AdaptiveStrategy | None:
        return self._adaptive_strategy

    @property
    def active(self) -> bool:
        "Check if any request groups have pending requests."
        return any(group.active for group in self._groups.values())

    async def __call__(self, pr: PRequest):
        "Process a request through the rate limiter."
        await self._handle(pr)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        try:
            await self.shutdown()
        finally:
            await self.close()

    async def shutdown(self) -> bool:
        if not self._stopped:
            if groups := self._groups.values():
                logger.info(
                    "Rate limiter: shutting down %d active group(s): %s",
                    len(groups),
                    ",".join(str(group.key) for group in groups),
                )
                for group in groups:
                    await group.put(PRequest(priority=sys.maxsize, request=Request(url="stub")))

            self._stopped = True
            return True

        return not self._stopped

    async def close(self):
        "Close all request groups and clean up resources."
        groups = list(self._groups.values())
        self._groups.clear()

        for group in groups:
            await group.close()

    def get_group_key(self, request: Request) -> Hashable:
        """Get group key for a request."""
        return self._group_by(request)[0]

    def on_request_outcome(self, outcome: RequestOutcome):
        """Handle request outcome and adjust group interval adaptively."""
        if not self._adaptive_strategy:
            return

        group = self._groups.get(outcome.group_key)
        if not group:
            return

        new_interval = self._adaptive_strategy.calculate_interval(
            group_key=outcome.group_key,
            current_interval=group.interval,
            outcome=outcome,
        )
        if new_interval != group.interval:
            group.set_intervals(interval=new_interval, cleanup_timeout=max(self._cleanup_timeout, new_interval * 2))

    async def _handle_with_group(self, pr: PRequest):
        group_key, interval = self._group_by(pr.request)

        # Ensure minimum interval to prevent busy-waiting. Custom group_by functions
        # may return zero or negative intervals, which we adjust to a safe minimum.
        if interval <= 0:
            logger.debug("Adjusting invalid interval %.3f to 0.01s for group %r", interval, group_key)
            interval = 0.01

        if (group := self._groups.get(group_key)) is None:
            group = self._groups[group_key] = self._create_group(group_key, interval)
            logger.debug(
                "Created rate limit group %r: interval=%0.10g, cleanup_timeout=%0.10g",
                group_key,
                interval,
                self._cleanup_timeout,
            )
        else:
            logger.debug("Queueing request to existing group %r (interval=%0.3fs)", group_key, group.interval)

        await group.put(pr)

    async def _handle_without_group(self, pr: PRequest):
        await self._schedule(pr)
        await asyncio.sleep(self._default_interval)

    def _create_group(self, key: Hashable, interval: float) -> RequestGroup:
        group = RequestGroup(
            key=key,
            interval=interval,
            cleanup_timeout=self._cleanup_timeout,
            schedule=self._schedule,
            on_finished=self._on_group_finished,
        )
        group.start_listening()
        return group

    def _on_group_finished(self, key: Hashable, group: RequestGroup):
        current = self._groups.get(key)
        if current is group:
            self._groups.pop(key, None)

            if self._adaptive_strategy:
                self._adaptive_strategy.reset_metrics(key)

            logger.debug("Rate limit group %r finished and removed (idle timeout or shutdown)", key)
