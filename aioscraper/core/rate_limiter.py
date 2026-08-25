import asyncio
import logging
import sys
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from time import monotonic
from typing import Any, Awaitable, Callable, Hashable, Self

from yarl import URL

from aioscraper.config import RateLimitConfig, RequestRetryConfig
from aioscraper.exceptions import ConnectionFailed, TransportTimeout
from aioscraper.types import GroupBy, GroupPolicy
from aioscraper.types.session import Attempt, Request

from .errors import ErrorCollector

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AdaptiveMetrics:
    """What one group's recent history looks like to :class:`AdaptiveStrategy`.

    Attributes:
        ewma_latency (float): Smoothed request latency in seconds.
        ewma_alpha (float): Weight of the newest sample (0 < alpha <= 1).
        success_count (int): Successes since the last failure.
        failure_count (int): Failures since the last success.
        last_outcome_time (float | None): Monotonic clock reading when the last request finished.
        last_outcome_success (bool): How the last request ended.
        total_requests (int): Requests this group has completed.
    """

    ewma_latency: float = 0.0
    ewma_alpha: float = 0.3
    success_count: int = 0
    failure_count: int = 0
    last_outcome_time: float | None = None
    last_outcome_success: bool = True
    total_requests: int = 0

    def update_latency(self, latency: float):
        "The first sample seeds the average: smoothed against 0.0 it would come out a fraction of itself."
        if self.total_requests == 0:
            self.ewma_latency = latency
        else:
            self.ewma_latency = (self.ewma_alpha * latency) + ((1 - self.ewma_alpha) * self.ewma_latency)

    def record_success(self, latency: float):
        "Extend the success streak and end the failure one."
        self.update_latency(latency)
        self.success_count += 1
        self.failure_count = 0
        self.last_outcome_success = True
        self.last_outcome_time = monotonic()
        self.total_requests += 1

    def record_failure(self, latency: float | None = None):
        "Extend the failure streak and end the success one. Latency is unknown when nothing came back."
        if latency is not None:
            self.update_latency(latency)

        self.failure_count += 1
        self.success_count = 0
        self.last_outcome_success = False
        self.last_outcome_time = monotonic()
        self.total_requests += 1


@dataclass(slots=True)
class RequestOutcome:
    """How one request ended, as the rate limiter sees it.

    Attributes:
        group_key (Hashable): Group the request was paced by.
        latency (float): Seconds from dispatch to the response or the failure.
        retry_after (float | None): Seconds the server asked for, when it sent a ``Retry-After``.
        status_code (int | None): Status of the response, absent when none arrived.
        exception_type (type[BaseException] | None): What the request raised, if anything.
    """

    group_key: Hashable
    latency: float
    retry_after: float | None = None
    status_code: int | None = None
    exception_type: type[BaseException] | None = None


class AdaptiveStrategy:
    """Picks a group's interval from how the last requests went, EWMA + AIMD.

    Backing off is multiplicative and immediate, recovering is additive and slow: pushback costs
    one failure, capacity is probed a step at a time.

    Args:
        min_interval (float): Floor for the interval, in seconds.
        max_interval (float): Ceiling for the interval, in seconds.
        increase_factor (float): The interval is multiplied by this on a failure.
        decrease_step (float): Seconds taken off after a run of successes.
        success_threshold (int): How many successes in a row it takes to step down.
        ewma_alpha (float): Weight of the newest latency sample (0 < alpha <= 1).
        trigger_statuses (tuple[int, ...]): Statuses that count as pushback.
        trigger_exceptions (tuple[type[BaseException], ...]): Exceptions that count as pushback.
        respect_retry_after (bool): Let a ``Retry-After`` header set the interval outright.
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
        trigger_exceptions: tuple[type[BaseException], ...] = (TransportTimeout, ConnectionFailed),
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
        if group_key not in self._metrics:
            self._metrics[group_key] = AdaptiveMetrics(ewma_alpha=self.ewma_alpha)

        return self._metrics[group_key]

    def calculate_interval(self, group_key: Hashable, current_interval: float, outcome: RequestOutcome) -> float:
        """Fold one outcome into the group's history and return the interval to use next.

        - a ``Retry-After`` the server sent wins outright, when ``respect_retry_after`` allows it
        - a failure multiplies the interval by ``increase_factor``
        - ``success_threshold`` successes in a row take ``decrease_step`` off it

        Returns:
            float: The new interval in seconds, clamped between ``min_interval`` and ``max_interval``.
        """
        metrics = self.get_or_create_metrics(group_key)

        success = not self._is_adaptive_failure(outcome.status_code, outcome.exception_type)

        if success:
            metrics.record_success(outcome.latency)
        else:
            metrics.record_failure(outcome.latency)

        # what the server asked for beats anything inferred from latency and counts
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

        if not success:
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
            new_interval = current_interval

        return max(self.min_interval, min(self.max_interval, new_interval))

    def reset_metrics(self, group_key: Hashable):
        "Forget a group's history once the group itself is gone."
        self._metrics.pop(group_key, None)

    def _is_adaptive_failure(self, status_code: int | None, exception_type: type[BaseException] | None) -> bool:
        "Whether this outcome reads as the server pushing back rather than as an ordinary failure."
        if status_code and status_code in self.trigger_statuses:
            return True

        if exception_type and any(issubclass(exception_type, exc_type) for exc_type in self.trigger_exceptions):
            return True

        return False


def default_group_by_factory(default_interval: float) -> GroupBy:
    "Group requests by hostname, every group at the same interval and the configured ceiling."

    def _group_by(request: Request) -> GroupPolicy:
        return GroupPolicy(key=URL(request.url).host or "unknown", interval=default_interval)

    return _group_by


class RequestGroup:
    """One rate-limited stream of requests.

    A worker task takes attempts off the group's queue one at a time and sleeps ``interval``
    between them, so the requests of a group never overlap in dispatch. The worker exits once the
    group has been idle for ``cleanup_timeout``, and the manager drops the group with it.

    With a ``concurrency`` ceiling the worker takes a permit before handing an attempt off, and
    blocks while the group has that many in flight. Held back here, at admission, rather than
    inside the request job: an attempt waiting on a permit occupies no scheduler slot.

    Args:
        key (Hashable): What the requests were grouped by, a hostname by default.
        interval (float): Seconds to wait after handing off one attempt.
        cleanup_timeout (float): Idle time before the group gives up its worker. Raised to twice
            ``interval`` when that is longer, so a slow group is not collected mid-stream.
        schedule (Callable[[Attempt], Awaitable[None]]): Hands an attempt to the scheduler.
        on_finished (Callable[[Hashable, RequestGroup], None]): Called when the worker stops, idle
            or crashed.
        concurrency (int): Ceiling on the group's requests in flight; ``0`` for no ceiling.
    """

    def __init__(
        self,
        key: Hashable,
        interval: float,
        cleanup_timeout: float,
        schedule: Callable[[Attempt], Awaitable[None]],
        on_finished: Callable[[Hashable, "RequestGroup"], None],
        error_collector: ErrorCollector | None = None,
        concurrency: int = 0,
    ):
        self._key = key
        self._interval = interval
        self._cleanup_timeout = max(cleanup_timeout, self._interval * 2)
        self._schedule = schedule
        self._on_finished = on_finished
        self._error_collector = ErrorCollector() if error_collector is None else error_collector
        self._queue: asyncio.PriorityQueue[Attempt] = asyncio.PriorityQueue()
        self._task: asyncio.Task[None] | None = None
        self._concurrency = concurrency
        self._permits = asyncio.Semaphore(concurrency) if concurrency else None
        self._in_flight = 0
        # keyed by identity: Attempt orders by priority, so equal attempts are not the same one
        self._admitted: dict[int, Attempt] = {}
        self._admission: asyncio.Task[None] | None = None

    @property
    def key(self) -> Hashable:
        return self._key

    @property
    def active(self) -> bool:
        "Whether anything is still queued or in flight."
        return not self._queue.empty() or self._in_flight > 0

    @property
    def in_flight(self) -> int:
        "Attempts handed off and not yet finished, plus the one the worker is admitting."
        return self._in_flight

    @property
    def concurrency(self) -> int:
        return self._concurrency

    @property
    def interval(self) -> float:
        return self._interval

    @property
    def worker_alive(self) -> bool:
        if self._task is None:
            return False

        return not self._task.done() and not self._task.cancelled()

    def set_intervals(self, interval: float, cleanup_timeout: float):
        "Retune the group. The worker picks the new values up on its next turn."
        self._interval = interval
        self._cleanup_timeout = cleanup_timeout

    async def put(self, attempt: Attempt):
        await self._queue.put(attempt)

    def start_listening(self):
        if self._task is not None:
            return

        self._task = asyncio.create_task(self._listen_queue())
        self._task.add_done_callback(self._on_task_done_factory())

    async def close(self):
        """Cancel the worker and settle what it was admitting. Anything still queued is dropped.

        A closed group holds no permits, including for a job the scheduler accepted but canceled
        before it could run.
        """
        if self._task is None:
            return

        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task

        await self._settle_admission()

        for attempt in tuple(self._admitted.values()):
            attempt.release_permit()

    async def _settle_admission(self):
        "Finish the hand-off the canceled worker left running, so no coroutine is left unawaited."
        admission, self._admission = self._admission, None
        if admission is None:
            return

        admission.cancel()
        try:
            await admission
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.exception("Rate limiter scheduler failed for %r while closing", self._key)
            self._error_collector.record("rate_limiter", exc)

    async def _listen_queue(self):
        while True:
            try:
                # An idle group is cleaned up after cleanup_timeout. Not wait_for: on
                # Python <= 3.11 it can swallow a close() cancellation arriving at the same time.
                async with asyncio.timeout(self._cleanup_timeout):
                    attempt = await self._queue.get()
            except asyncio.TimeoutError:
                # something may have been queued while the timeout was firing; collecting a group
                # with requests in flight would hand the next group of that key a full ceiling
                # beside them
                if not self._queue.empty() or self._in_flight:
                    continue

                # the worker's done callback reports it: breaking here is not a cancellation
                break

            # the sentinel RateLimitManager.shutdown() queues behind the real work
            if attempt.request.url == "stub":
                break

            await self._acquire_permit(attempt)

            # kept on the group: the shield leaves it running when the worker is canceled, and
            # close() has to settle it
            admission = asyncio.ensure_future(self._schedule(attempt))
            self._admission = admission

            try:
                await asyncio.shield(admission)
            except Exception as exc:
                logger.exception("Rate limiter scheduler failed for %r", self._key)
                self._error_collector.record("rate_limiter", exc)
                # the job never started, so nothing downstream will give the permit back
                attempt.release_permit()

            # skipped when the worker is canceled, leaving close() the admission to settle
            self._admission = None

            await asyncio.sleep(self._interval)

    async def _acquire_permit(self, attempt: Attempt):
        "Take the group's permit for this attempt, waiting while the group is at its ceiling."
        # Counted and reclaimable from here rather than from the acquire below: an attempt
        # waiting for a permit sits in no queue and no scheduler, so a run that cannot see it
        # declares itself finished.
        self._in_flight += 1
        self._admitted[id(attempt)] = attempt
        attempt.permit_release = partial(self._drop_attempt, attempt)

        if self._permits is not None:
            if self._permits.locked():
                logger.debug(
                    "Rate limit group %r at its concurrency ceiling of %d, waiting for a permit",
                    self._key,
                    self._concurrency,
                )

            await self._permits.acquire()

        attempt.permit_release = partial(self._release_permit, attempt)

    def _drop_attempt(self, attempt: Attempt):
        "Let go of an attempt that never got as far as taking a permit."
        self._admitted.pop(id(attempt), None)
        self._in_flight -= 1

    def _release_permit(self, attempt: Attempt):
        self._drop_attempt(attempt)
        if self._permits is not None:
            self._permits.release()

    def _on_task_done_factory(self) -> Callable[[asyncio.Task[None]], None]:
        def _on_task_done(task: asyncio.Task[None]):
            if task.cancelled():
                logger.debug("Rate limiter group %r canceled", self._key)
                return

            with suppress(asyncio.CancelledError):
                exc = task.exception()

            if exc is not None:
                logger.error("Rate limiter group %r crashed: %s", self._key, exc, exc_info=exc)
                self._error_collector.record("rate_limiter", exc)

            self._on_finished(self._key, self)

        return _on_task_done


class RateLimitManager:
    """Paces requests by group, creating and retiring the groups as traffic comes and goes.

    A group is made the first time its key is seen and disappears once it has been idle for
    ``cleanup_timeout``. With rate limiting off, requests go straight to the scheduler, separated
    only by ``default_interval`` if one is set.

    Args:
        config (RateLimitConfig): Grouping function, intervals and the adaptive settings.
        retry_config (RequestRetryConfig): Read for its triggers when
            ``adaptive.inherit_retry_triggers`` is on.
        schedule (Callable[[Attempt], Awaitable[Any]]): Hands an attempt to the scheduler.
        error_collector (ErrorCollector | None): Records what a group's worker failed with.
        group_by (GroupBy | None): Maps a request to its group key, that group's interval and its
            concurrency ceiling; ``None`` groups by hostname at ``config.default_interval``.
    """

    def __init__(
        self,
        config: RateLimitConfig,
        retry_config: RequestRetryConfig,
        schedule: Callable[[Attempt], Awaitable[Any]],
        error_collector: ErrorCollector | None = None,
        group_by: GroupBy | None = None,
    ):
        self._schedule = schedule
        self._error_collector = ErrorCollector() if error_collector is None else error_collector
        self._group_by = group_by or default_group_by_factory(config.default_interval)
        self._default_interval = config.default_interval
        self._cleanup_timeout = config.cleanup_timeout
        self._group_concurrency = config.group_concurrency
        self._groups: dict[Hashable, RequestGroup] = {}
        self._enabled = config.per_group
        self._stopped = False

        self._adaptive_strategy: AdaptiveStrategy | None = None
        if config.per_group and config.adaptive:
            trigger_statuses = config.adaptive.custom_trigger_statuses
            trigger_exceptions = config.adaptive.custom_trigger_exceptions

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

        if config.per_group:
            self._handle = self._handle_with_group
            logger.info(
                "Rate limiting per group: grouping=%s, default_interval=%0.10g, cleanup_timeout=%0.10g, "
                "group_concurrency=%s",
                "custom" if group_by else "by hostname",
                self._default_interval,
                self._cleanup_timeout,
                self._group_concurrency or "unlimited",
            )
        else:
            self._handle = self._handle_without_group
            if self._default_interval > 0:
                logger.info(
                    "Rate limiting across the run: default_interval=%0.10g",
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
        "Whether any group still has work queued."
        return any(group.active for group in self._groups.values())

    async def __call__(self, attempt: Attempt):
        "Route an attempt to its group, or straight to the scheduler when grouping is off."
        await self._handle(attempt)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *args: object) -> None:
        try:
            await self.shutdown()
        finally:
            await self.close()

    async def shutdown(self) -> bool:
        """Queue a stop sentinel behind whatever each group still holds.

        Returns:
            bool: ``True`` from the call that stopped it, ``False`` from every later one.
        """
        if not self._stopped:
            if groups := self._groups.values():
                logger.info(
                    "Rate limiter: shutting down %d active group(s): %s",
                    len(groups),
                    ",".join(str(group.key) for group in groups),
                )
                for group in groups:
                    await group.put(Attempt(priority=sys.maxsize, request=Request(url="stub")))

            self._stopped = True
            return True

        return not self._stopped

    async def close(self):
        "Cancel every group's worker, dropping whatever is still queued."
        groups = list(self._groups.values())
        self._groups.clear()

        for group in groups:
            await group.close()

    def get_group_key(self, request: Request) -> Hashable:
        return self._group_by(request)[0]

    def on_request_outcome(self, outcome: RequestOutcome):
        "Retune the group this request belongs to. A group already retired is left alone."
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

    async def _handle_with_group(self, attempt: Attempt):
        group_key, interval, concurrency = self._group_by(attempt.request)

        # a custom group_by can hand back zero or less, which would spin the group's worker
        if interval <= 0:
            logger.debug("Adjusting invalid interval %.3f to 0.01s for group %r", interval, group_key)
            interval = 0.01

        concurrency = self._resolve_concurrency(group_key, concurrency)

        # a retired group outlives its worker: the done callback removes it a tick later, and an
        # attempt queued in between would have nothing to read it
        group = self._groups.get(group_key)
        if group is None or not group.worker_alive:
            group = self._groups[group_key] = self._create_group(group_key, interval, concurrency)
            logger.debug(
                "Created rate limit group %r: interval=%0.10g, cleanup_timeout=%0.10g, concurrency=%d",
                group_key,
                interval,
                self._cleanup_timeout,
                concurrency,
            )
        else:
            if concurrency != group.concurrency:
                # resizing it under the requests already counted against it would let the group
                # exceed both the old ceiling and the new one
                logger.warning(
                    "Rate limit group %r runs with concurrency=%d; the %d from group_by applies "
                    "only to a group created later",
                    group_key,
                    group.concurrency,
                    concurrency,
                )

            logger.debug("Queueing request to existing group %r (interval=%0.3fs)", group_key, group.interval)

        await group.put(attempt)

    def _resolve_concurrency(self, group_key: Hashable, concurrency: int | None) -> int:
        "Fall back to the configured ceiling when none was asked for, or when the one asked for makes no sense."
        if concurrency is None:
            return self._group_concurrency

        if concurrency < 0:
            logger.warning(
                "Invalid concurrency %d from group_by for group %r, using the configured %d",
                concurrency,
                group_key,
                self._group_concurrency,
            )
            return self._group_concurrency

        return concurrency

    async def _handle_without_group(self, attempt: Attempt):
        await self._schedule(attempt)
        await asyncio.sleep(self._default_interval)

    def _create_group(self, key: Hashable, interval: float, concurrency: int) -> RequestGroup:
        group = RequestGroup(
            key=key,
            interval=interval,
            cleanup_timeout=self._cleanup_timeout,
            schedule=self._schedule,
            on_finished=self._on_group_finished,
            error_collector=self._error_collector,
            concurrency=concurrency,
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
