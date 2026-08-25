import asyncio
import codecs
import heapq
from contextlib import AsyncExitStack, suppress
from functools import partial
from logging import getLogger
from math import isfinite
from time import monotonic
from typing import Any

from aiojobs import Scheduler

from aioscraper._helpers.asyncio import execute_coroutine, execute_coroutines
from aioscraper._helpers.func import get_func_kwargs
from aioscraper._helpers.http import parse_retry_after, parse_url
from aioscraper.config import RateLimitConfig, RequestRetryConfig, SchedulerConfig
from aioscraper.exceptions import AIOScraperException, HTTPException, InvalidRequestData, InvalidURL
from aioscraper.holders import MiddlewareHolder
from aioscraper.types import GroupBy, RequestHandler, RequestMiddleware, Response, ShouldRetry
from aioscraper.types.session import DEFAULT_MAX_ERROR_BODY_SIZE, Attempt, Request, ScheduleRequest

from .errors import ErrorCollector
from .rate_limiter import RateLimitManager, RequestOutcome
from .retry import RetryPolicy
from .session import SessionMaker
from .stats import RunStats

logger = getLogger(__name__)


_RequestQueue = asyncio.PriorityQueue[Attempt]
_RequestHead = list[Attempt]


async def _raise_for_status(request: Request, response: Response, max_error_body_size: int):
    "Raise :class:`HTTPException` when the response carries a non-ok status."
    if response.ok:
        return

    message = ""
    if max_error_body_size > 0:
        # the body only feeds the exception message, so it is read bounded — and by this budget
        # rather than max_response_body_size, which bounds what a callback may receive
        body = await response._read_limited(max_error_body_size + 1)
        message = body[:max_error_body_size].decode(response.get_encoding(), errors="replace")
        if len(body) > max_error_body_size:
            message += " [truncated]"

    raise HTTPException(
        url=str(parse_url(request.url, request.params)),
        method=response.method,
        headers=response.headers,
        status_code=response.status,
        message=message,
    )


class _PendingSlots:
    "Counts requests accepted but not yet handed to the scheduler. A limit of 0 disables counting."

    def __init__(self, limit: int):
        self._limit = limit
        self._count = 0
        self._space = asyncio.Condition()

    @property
    def count(self) -> int:
        return self._count

    async def acquire(self, *, wait: bool) -> bool:
        if not self._limit:
            return False

        async with self._space:
            if wait:
                await self._space.wait_for(lambda: self._count < self._limit)

            self._count += 1

        return True

    async def release(self, attempt: Attempt):
        if not attempt.holds_slot:
            return

        attempt.holds_slot = False
        async with self._space:
            self._count -= 1
            self._space.notify_all()


async def _admit(
    queue: _RequestQueue,
    heap: _RequestHead,
    slots: _PendingSlots,
    request: Request,
    *,
    delay: float | None,
    wait_for_slot: bool,
    retries: int = 0,
) -> None:
    "Queue one attempt of a request, on the delayed heap when it must wait first."
    # Taken before the slot is acquired: waiting for admission must not extend the delay.
    now = monotonic()
    holds_slot = await slots.acquire(wait=wait_for_slot)

    if delay:
        heapq.heappush(
            heap,
            Attempt(priority=now + delay, request=request, holds_slot=holds_slot, retries=retries),
        )
    else:
        queue.put_nowait(
            Attempt(priority=request.priority, request=request, holds_slot=holds_slot, retries=retries),
        )


def _log_url(request: Request) -> str:
    "The URL as it will be sent, or the raw one when it does not parse: logging must not fail."
    try:
        return str(parse_url(request.url, request.params))
    except ValueError:
        return request.url


def _validate(request: Request):
    """Reject a request no backend could send, whoever built it."""
    try:
        parse_url(request.url, request.params)
    except ValueError as exc:
        # otherwise it surfaces from yarl deeper in, where no errback and no counter reach it
        raise InvalidURL(request.url, request.method, str(exc)) from exc

    if request.json_data is not None and request.data is not None:
        raise InvalidRequestData("Cannot send both data and json_data")

    if request.json_data is not None and request.files is not None:
        raise InvalidRequestData("Cannot send both files and json_data")

    # backends disagree on what a non-positive timeout means; None is how a request asks for the session's
    if request.timeout is not None and not (isfinite(request.timeout) and request.timeout > 0):
        raise InvalidRequestData(f"Request timeout must be a positive number of seconds, got {request.timeout!r}")

    # a codec that does not exist is a broken request, not a backend limitation
    for field in ("auth", "proxy_auth"):
        credentials = getattr(request, field)
        if credentials is None or (encoding := credentials.get("encoding")) is None:
            continue

        try:
            codecs.lookup(encoding)
        except LookupError:
            raise InvalidRequestData(f"Unknown {field} encoding: {encoding}") from None


def _get_request_sender(
    queue: _RequestQueue,
    heap: _RequestHead,
    slots: _PendingSlots,
    *,
    wait_for_slot: bool,
) -> ScheduleRequest:
    "Creates a request sender. Only the entrypoint variant waits for a free slot."

    async def sender(request: Request) -> Request:
        _validate(request)
        await _admit(queue, heap, slots, request, delay=request.delay, wait_for_slot=wait_for_slot)
        return request

    return sender


class RequestManager:
    """Carries a request from ``schedule_request`` to its callback.

    Accepted requests wait in a priority queue, or on a heap when they were given a delay. A
    listener task moves them through the rate limiter to the scheduler, which runs the middleware
    chain and the dispatch inside it. A failure the retry policy accepts is admitted again instead
    of reaching the errback.

    Args:
        scheduler_config (SchedulerConfig): Concurrency limits and the admission cap.
        rate_limit_config (RateLimitConfig): How requests are grouped and paced.
        retry_config (RequestRetryConfig): What is retried, how often and after how long.
        shutdown_check_interval (float): How long the listener may block before rechecking whether
            the run is over.
        sessionmaker (SessionMaker): Builds the HTTP session requests are sent through.
        dependencies (dict[str, Any]): Injected into middleware factories, callbacks and errbacks
            by parameter name.
        middleware_holder (MiddlewareHolder): The registered request middleware factories.
        error_collector (ErrorCollector | None): Records errors that are logged and dropped.
        max_error_body_size (int): Bytes of a failed response read into the ``HTTPException`` message.
        stats (RunStats | None): Counts attempts for the run's outcome.
        buffer_body (bool): Whether to read a body before the callback runs, unless the request says.
        group_by (GroupBy | None): Maps a request to its rate limit group, interval and ceiling.
        should_retry (ShouldRetry | None): Decides a failure the retry config cannot express.
    """

    def __init__(
        self,
        scheduler_config: SchedulerConfig,
        rate_limit_config: RateLimitConfig,
        retry_config: RequestRetryConfig,
        shutdown_check_interval: float,
        sessionmaker: SessionMaker,
        dependencies: dict[str, Any],
        middleware_holder: MiddlewareHolder,
        error_collector: ErrorCollector | None = None,
        max_error_body_size: int = DEFAULT_MAX_ERROR_BODY_SIZE,
        stats: RunStats | None = None,
        *,
        buffer_body: bool = False,
        group_by: GroupBy | None = None,
        should_retry: ShouldRetry | None = None,
    ):
        self._error_collector = ErrorCollector() if error_collector is None else error_collector
        self._stats = RunStats() if stats is None else stats
        self._max_error_body_size = max_error_body_size
        self._buffer_body = buffer_body
        logger.info(
            "Creating scheduler: concurrent_requests=%s, pending_requests=%s, close_timeout=%s",
            scheduler_config.concurrent_requests,
            scheduler_config.pending_requests,
            scheduler_config.close_timeout,
        )
        self._scheduler = Scheduler(
            limit=scheduler_config.concurrent_requests,
            pending_limit=scheduler_config.pending_requests,
            close_timeout=scheduler_config.close_timeout,
        )
        self._shutdown_check_interval = shutdown_check_interval
        self._session = sessionmaker()
        # A maxsize would deadlock: _pop_due_delayed fills it from its only consumer.
        self._ready_queue: _RequestQueue = asyncio.PriorityQueue()
        self._delayed_heap: _RequestHead = []
        self._pending_slots = _PendingSlots(scheduler_config.ready_queue_max_size)
        self._request_sender = _get_request_sender(
            self._ready_queue,
            self._delayed_heap,
            self._pending_slots,
            wait_for_slot=True,
        )
        # A job holds a scheduler slot, and slots free up through the scheduler: waiting deadlocks.
        self._job_sender = _get_request_sender(
            self._ready_queue,
            self._delayed_heap,
            self._pending_slots,
            wait_for_slot=False,
        )
        self._dependencies: dict[str, Any] = {
            "schedule_request": self._job_sender,
            # deprecated alias of schedule_request, removed in 1.0
            "send_request": self._job_sender,
            **dependencies,
        }
        self._middleware_holder = middleware_holder
        self._rate_limiter_manager = RateLimitManager(
            rate_limit_config,
            retry_config=retry_config,
            schedule=self._schedule,
            error_collector=self._error_collector,
            group_by=group_by,
        )
        self._retry_policy = RetryPolicy(retry_config, should_retry=should_retry)
        self._middlewares: list[RequestMiddleware] = self._instantiate_middlewares()
        self._initialized = False
        self._completed = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def sender(self) -> ScheduleRequest:
        return self._request_sender

    async def _run_attempt(self, attempt: Attempt):
        """Run one attempt as a scheduler job.

        Wraps the call rather than passing ``self._send_request(attempt)`` to
        :func:`execute_coroutine` at the spawn: that builds the inner coroutine before the job is
        accepted, and a job the scheduler never runs leaves it unawaited.
        """
        await execute_coroutine(
            self._send_request(attempt),
            on_error=partial(self._error_collector.record, "request"),
        )

    async def _schedule(self, attempt: Attempt):
        "Hand an attempt to the scheduler and free the slot it held while queued."
        job = self._run_attempt(attempt)
        try:
            await self._scheduler.spawn(job)
        except BaseException:
            # spawn rejects a closed scheduler before it wraps the coroutine in a job, so nothing
            # will ever run it; closing it here keeps it from being reported unawaited
            job.close()
            raise
        finally:
            await self._pending_slots.release(attempt)

    @property
    def error_collector(self) -> ErrorCollector:
        return self._error_collector

    def _instantiate_middlewares(self) -> list[RequestMiddleware]:
        "Instantiate registered middleware factories once, injecting dependencies."
        middlewares: list[RequestMiddleware] = []
        for factory in self._middleware_holder:
            try:
                middlewares.append(factory(**get_func_kwargs(factory, **self._dependencies)))
            except Exception as exc:
                raise AIOScraperException(
                    f"Failed to instantiate request middleware factory {factory!r}",
                ) from exc

        return middlewares

    def _build_handler(self, stack: AsyncExitStack, attempt: Attempt) -> RequestHandler:
        "Compose the middleware chain around the innermost dispatch."

        async def dispatch(request: Request) -> Response | None:
            # Revalidated: a middleware can change the request after it was queued. Outside the
            # try, like the build: a rejection is a contract error, not a transport outcome.
            _validate(request)
            request_ctx = self._session.make_request(request)

            start_time = monotonic()
            status_code = exception_type = retry_after = None

            try:
                response = await stack.enter_async_context(request_ctx)
                status_code = response.status
                await _raise_for_status(request, response, self._max_error_body_size)

                if request.buffer_body is True or (request.buffer_body is None and self._buffer_body):
                    await response.read()
            except Exception as exc:
                exception_type = type(exc)

                if isinstance(exc, HTTPException):
                    status_code = exc.status_code
                    if self._rate_limiter_manager.adaptive_strategy:
                        retry_after = parse_retry_after(exc)

                raise
            else:
                return response
            finally:
                # Recorded here, not around the chain: a middleware or the retry decision above
                # can swallow the failure before it gets there.
                self._record_outcome(
                    attempt,
                    latency=monotonic() - start_time,
                    status_code=status_code,
                    exception_type=exception_type,
                    retry_after=retry_after,
                )

        handler: RequestHandler = dispatch
        for middleware in reversed(self._middlewares):
            next_handler = handler

            async def wrapped(
                request: Request,
                _mw: RequestMiddleware = middleware,
                _next: RequestHandler = next_handler,
            ) -> Response | None:
                return await _mw(_next, request)

            handler = wrapped

        return handler

    async def _retry(self, attempt: Attempt, exc: Exception) -> bool:
        "Admit the request again when the retry policy allows it, reporting whether it was."
        request = attempt.request
        delay = self._retry_policy.next_delay(request, exc, attempt.retries)
        if delay is None:
            return False

        retries = attempt.retries + 1
        logger.debug("Retrying %s %s in %0.10gs (retry %d)", request.method, request.url, delay, retries)
        # Never waits for a slot: this runs inside a request job, and slots free up through
        # the scheduler.
        await _admit(
            self._ready_queue,
            self._delayed_heap,
            self._pending_slots,
            request,
            delay=delay,
            wait_for_slot=False,
            retries=retries,
        )
        # counted once the attempt is queued: a canceled admission is not a retry
        self._stats.request_retried()
        return True

    def _record_outcome(
        self,
        attempt: Attempt,
        *,
        latency: float,
        status_code: int | None,
        exception_type: type[BaseException] | None,
        retry_after: float | None,
    ):
        "Feed a transport outcome to the adaptive rate limiter, under the key it was routed with."
        # not guarded on the key: adaptive needs per_group, which routes every attempt, and None
        # is a group key like any other
        if not self._rate_limiter_manager.adaptive_strategy:
            return

        self._rate_limiter_manager.on_request_outcome(
            RequestOutcome(
                group_key=attempt.group_key,
                latency=latency,
                retry_after=retry_after,
                status_code=status_code,
                exception_type=exception_type,
            ),
        )

    async def _send_request(self, attempt: Attempt):
        request = attempt.request
        start_time = monotonic()
        url = _log_url(request)
        self._stats.request_started()

        try:
            async with AsyncExitStack() as stack:
                handler = self._build_handler(stack, attempt)

                logger.debug("Sending request: %s %s", request.method, url)
                try:
                    response = await handler(request)
                except Exception as exc:
                    # Wraps the chain rather than dispatch, so a middleware turning a 200 into a
                    # failure is retried too. The callback below stays outside: failing to process
                    # a response is no reason to fetch it again.
                    if await self._retry(attempt, exc):
                        return

                    raise

                if response is None:
                    logger.debug(
                        "Request handled without a response: %s %s",
                        request.method,
                        url,
                    )
                    return

                logger.debug(
                    "Response received: %s %s - status=%d, latency=%.3fs",
                    request.method,
                    url,
                    response.status,
                    monotonic() - start_time,
                )

                await self._callback(request, response)
                self._stats.request_succeeded()
        except Exception as exc:
            self._stats.request_failed()
            logger.debug("Request exception: %s %s - %s: %s", request.method, url, type(exc).__name__, exc)
            await self._handle_exception(request, exc)
        finally:
            # Covers the same span as the scheduler slot, callback included, so that a group's
            # ceiling means the same thing as its share of concurrent_requests.
            attempt.release_permit()

    async def _callback(self, request: Request, response: Response):
        if request.callback is None:
            return

        # built rather than unpacked at the call: duplicate keys across two ** is a TypeError,
        # and cb_kwargs is free-form
        kwargs = {**self._dependencies, **request.cb_kwargs, "request": request, "response": response}
        if hasattr(request.callback, "__compiled__"):
            await request.callback(**kwargs)
        else:
            await request.callback(**get_func_kwargs(request.callback, **kwargs))

    async def _handle_exception(self, request: Request, exc: Exception):
        if request.errback is not None:
            kwargs = {**self._dependencies, **request.cb_kwargs, "request": request, "exc": exc}
            try:
                if hasattr(request.errback, "__compiled__"):
                    await request.errback(**kwargs)
                else:
                    await request.errback(**get_func_kwargs(request.errback, **kwargs))
            except Exception as errback_exc:
                logger.exception(
                    "Errback failed for %s %s: original=%s, errback=%s",
                    request.method,
                    request.url,
                    type(exc).__name__,
                    type(errback_exc).__name__,
                )
                raise ExceptionGroup("Errback failed", [exc, errback_exc]) from None
        else:
            logger.error("%s: %s: %s", request.method, request.url, exc, exc_info=exc)
            self._error_collector.record("request", exc)

    async def wait(self):
        logger.debug("Request manager waiting for completion")
        self._initialized = True
        await self._completed.wait()
        logger.debug("Request manager wait completed")

    async def shutdown(self):
        logger.debug("Request manager shutting down")

        self._initialized = True
        if self._task is not None:
            await self._task

        logger.debug("Request manager shutdown completed")

    def start_listening(self):
        logger.debug("Request manager starting queue listener")
        self._task = asyncio.create_task(self._listen_queue())

    async def _listen_queue(self):
        "Feed queued attempts to the rate limiter until nothing is left anywhere to run."
        while (
            not self._initialized
            or len(self._scheduler) > 0
            or self._rate_limiter_manager.active
            or not self._ready_queue.empty()
            or len(self._delayed_heap) > 0
            or await self._rate_limiter_manager.shutdown()
        ):
            await self._pop_due_delayed()

            # Not wait_for: on Python <= 3.11 it cancels through a wrapper task and loses a
            # close() cancellation landing in the same iteration as the timeout.
            try:
                async with asyncio.timeout(self._next_timeout()):
                    attempt = await self._ready_queue.get()
            except asyncio.TimeoutError:
                continue

            try:
                await asyncio.shield(self._rate_limiter_manager(attempt))
            except asyncio.CancelledError:
                logger.debug("Queue listener canceled")
                break

        self._completed.set()
        logger.info("Queue listener completed: all requests processed")

    async def _pop_due_delayed(self):
        """Pop every due attempt from the delayed heap."""
        now = monotonic()
        while self._delayed_heap and self._delayed_heap[0].priority <= now:
            await self._ready_queue.put(heapq.heappop(self._delayed_heap))

    def _next_timeout(self) -> float:
        "Capped at the shutdown check interval: the heap can change while the listener waits."
        if not self._delayed_heap:
            return self._shutdown_check_interval

        timeout = self._delayed_heap[0].priority - monotonic()
        return max(0.0, min(timeout, self._shutdown_check_interval))

    async def close(self):
        """Stop the queue listener and close the underlying resources."""
        # Without this a listener left running after close() fails on closed resources,
        # and the exception surfaces later as an unretrieved task exception.
        if self._task is not None and not self._task.done():
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task

        await execute_coroutines(
            self._rate_limiter_manager.close(),
            self._scheduler.close(),
            self._session.close(),
            on_error=partial(self._error_collector.record, "close"),
        )
        logger.debug("Request manager closed successfully")
