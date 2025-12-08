import asyncio
import logging
from contextlib import suppress
from typing import Any, Awaitable, Callable, Hashable

from yarl import URL

from ..config import RateLimitConfig
from ..types.session import Request, PRequest


logger = logging.getLogger(__name__)


def _default_group_by_factory(default_interval: float) -> Callable[[Request], tuple[Hashable, float]]:
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
        self._task: asyncio.Task[None] = asyncio.create_task(self._worker())
        self._task.add_done_callback(self._on_task_done_factory())

    @property
    def active(self) -> bool:
        "Check if the group has pending requests in its queue."
        return not self._queue.empty()

    async def put(self, pr: PRequest):
        "Add a request to this group's processing queue."
        await self._queue.put(pr)

    async def close(self):
        "Cancel the worker task and wait for graceful shutdown."
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task

    async def _worker(self):
        try:
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

                try:
                    await self._schedule(pr)
                except Exception as e:
                    logger.error("Rate limiter scheduler failed for %r: %s", self._key, e, exc_info=e)

                await asyncio.sleep(self._interval)
        except asyncio.CancelledError:
            raise

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


class RateLimiterManager:
    """Manages rate limiting for requests using group-based throttling.

    Requests are grouped by a configurable key (default: hostname) and processed
    with a specified interval between requests in each group. Groups are created
    dynamically and cleaned up automatically after inactivity.

    Args:
        config (RateLimitConfig): Rate limiting configuration including grouping strategy and intervals.
        schedule (Callable[[PRequest], Awaitable[Any]]): Callback function to schedule request execution.
    """

    def __init__(self, config: RateLimitConfig, schedule: Callable[[PRequest], Awaitable[Any]]):
        self._schedule = schedule
        self._group_by = config.group_by or _default_group_by_factory(config.default_interval)
        self._default_interval = config.default_interval
        self._cleanup_timeout = config.cleanup_timeout
        self._groups: dict[Hashable, RequestGroup] = {}
        self._enabled = config.enabled

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

    async def __call__(self, pr: PRequest):
        "Process a request through the rate limiter."
        await self._handle(pr)

    async def _handle_with_group(self, pr: PRequest):
        group_key, interval = self._group_by(pr.request)

        # Ensure minimum interval to prevent busy-waiting. Custom group_by functions
        # may return zero or negative intervals, which we adjust to a safe minimum.
        if interval <= 0:
            interval = 0.01

        if (group := self._groups.get(group_key)) is None:
            group = self._groups[group_key] = self._create_group(group_key, interval)
            logger.debug(
                "Created rate limit group %r: interval=%0.10g, cleanup_timeout=%0.10g",
                group_key,
                interval,
                self._cleanup_timeout,
            )

        await group.put(pr)

    async def _handle_without_group(self, pr: PRequest):
        await self._schedule(pr)
        await asyncio.sleep(self._default_interval)

    def _create_group(self, key: Hashable, interval: float) -> RequestGroup:
        return RequestGroup(
            key=key,
            interval=interval,
            cleanup_timeout=self._cleanup_timeout,
            schedule=self._schedule,
            on_finished=self._on_group_finished,
        )

    def _on_group_finished(self, key: Hashable, group: RequestGroup):
        current = self._groups.get(key)
        if current is group:
            self._groups.pop(key, None)
            logger.debug("Rate limit group %r finished and removed (idle timeout or shutdown)", key)

    @property
    def active(self) -> bool:
        "Check if any request groups have pending requests."
        return any(group.active for group in self._groups.values())

    async def close(self):
        "Close all request groups and clean up resources."
        groups = list(self._groups.values())
        self._groups.clear()

        if groups:
            logger.info("Closing rate limiter: shutting down %d active group(s)", len(groups))
            for group in groups:
                await group.close()
        else:
            logger.debug("Closing rate limiter: no active groups")
