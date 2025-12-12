import asyncio
import heapq
from logging import getLogger
from time import monotonic
from typing import Any

from aiojobs import Scheduler

from aioscraper._helpers.asyncio import execute_coroutine, execute_coroutines
from aioscraper._helpers.func import get_func_kwargs
from aioscraper._helpers.http import parse_retry_after, parse_url
from aioscraper._helpers.log import get_log_name
from aioscraper.config import RateLimitConfig, RequestRetryConfig, SchedulerConfig
from aioscraper.exceptions import HTTPException, InvalidRequestData, StopMiddlewareProcessing, StopRequestProcessing
from aioscraper.holders import MiddlewareHolder
from aioscraper.types import Response
from aioscraper.types.session import PRequest, Request, SendRequest

from .rate_limiter import RateLimitManager, RequestOutcome
from .session import SessionMaker

logger = getLogger(__name__)


_RequestQueue = asyncio.PriorityQueue[PRequest]
_RequestHead = list[PRequest]


def _get_request_sender(queue: _RequestQueue, heap: _RequestHead) -> SendRequest:
    "Creates a request sender function that adds requests to the priority queue."

    async def sender(request: Request) -> Request:
        now = monotonic()
        if request.json_data is not None and request.data is not None:
            raise InvalidRequestData("Cannot send both data and json_data")

        if request.json_data is not None and request.files is not None:
            raise InvalidRequestData("Cannot send both files and json_data")

        if request.delay:
            heapq.heappush(heap, PRequest(priority=now + request.delay, request=request))
        else:
            await queue.put(PRequest(priority=request.priority, request=request))

        return request

    return sender


class RequestManager:
    """
    Manages HTTP requests with priority queuing, rate limiting, and middleware support.

    Args:
        scheduler_config (SchedulerConfig): Configuration for the request scheduler.
        rate_limit_config (RateLimitConfig): Configuration for the request rate limiter.
        retry_config (RequestRetryConfig): Configuration for request retries.
        shutdown_check_interval (float): Interval between shutdown checks in seconds
        sessionmaker (SessionMaker): A factory for creating session objects.
        dependencies (dict[str, Any]): Additional dependencies to be injected into middleware and callbacks.
        middleware_holder (MiddlewareHolder): A container for middleware collections.
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
    ):
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
        self._ready_queue: _RequestQueue = asyncio.PriorityQueue(maxsize=scheduler_config.ready_queue_max_size)
        self._delayed_heap: _RequestHead = []
        self._request_sender = _get_request_sender(self._ready_queue, self._delayed_heap)
        self._dependencies: dict[str, Any] = {"send_request": self._request_sender, **dependencies}
        self._middleware_holder = middleware_holder
        self._rate_limiter_manager = RateLimitManager(
            rate_limit_config,
            retry_config=retry_config,
            schedule=lambda pr: self._scheduler.spawn(execute_coroutine(self._send_request(pr.request))),
        )
        self._initialized = False
        self._completed = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def sender(self) -> SendRequest:
        return self._request_sender

    async def _send_request(self, request: Request):
        start_time = monotonic()
        latency = status_code = exception_type = retry_after = None
        url = parse_url(request.url, request.params)

        try:
            for inner_middleware in self._middleware_holder.inner:
                try:
                    await inner_middleware(**get_func_kwargs(inner_middleware, request=request, **self._dependencies))
                except StopRequestProcessing:
                    logger.debug("StopRequestProcessing in inner middleware for %s %s: aborting", request.method, url)
                    return
                except StopMiddlewareProcessing:
                    logger.debug(
                        "StopMiddlewareProcessing in inner middleware for %s %s: stopping inner chain",
                        request.method,
                        url,
                    )
                    break

            logger.debug("Sending request: %s %s", request.method, url)

            async with self._session.make_request(request) as response:
                latency = monotonic() - start_time  # response latency
                logger.debug(
                    "Response received: %s %s - status=%d, latency=%.3fs",
                    request.method,
                    url,
                    response.status,
                    latency,
                )

                for response_middleware in self._middleware_holder.response:
                    try:
                        await response_middleware(
                            **get_func_kwargs(
                                response_middleware,
                                request=request,
                                response=response,
                                **self._dependencies,
                            ),
                        )
                    except StopRequestProcessing:
                        logger.debug(
                            "StopRequestProcessing in response middleware for %s %s: aborting",
                            request.method,
                            url,
                        )
                        return
                    except StopMiddlewareProcessing:
                        logger.debug(
                            "StopMiddlewareProcessing in response middleware for %s %s: stopping response chain",
                            request.method,
                            url,
                        )
                        break

                if response.ok:
                    await self._callback(request, response)
                else:
                    http_exc = HTTPException(
                        url=str(url),
                        method=response.method,
                        headers=response.headers,
                        status_code=response.status,
                        message=await response.text(errors="replace"),
                    )
                    status_code = http_exc.status_code
                    exception_type = HTTPException

                    logger.debug(
                        "HTTP error: %s %s - status=%d, latency=%.3fs",
                        request.method,
                        url,
                        status_code,
                        latency,
                    )

                    if self._rate_limiter_manager.adaptive_strategy:
                        retry_after = parse_retry_after(http_exc)

                    await self._handle_exception(request, http_exc)
        except Exception as exc:
            exception_type = type(exc)
            logger.debug("Request exception: %s %s - %s: %s", request.method, url, type(exc).__name__, exc)
            await self._handle_exception(request, exc)
        finally:
            # Send feedback to adaptive rate limiter
            if self._rate_limiter_manager.adaptive_strategy:
                if latency is None:
                    latency = monotonic() - start_time

                self._rate_limiter_manager.on_request_outcome(
                    RequestOutcome(
                        group_key=self._rate_limiter_manager.get_group_key(request),
                        latency=latency,
                        retry_after=retry_after,
                        status_code=status_code,
                        exception_type=exception_type,
                    ),
                )

    async def _callback(self, request: Request, response: Response):
        if request.callback is None:
            return

        if hasattr(request.callback, "__compiled__"):
            await request.callback(
                request=request,
                response=response,
                **request.cb_kwargs,
                **self._dependencies,
            )
        else:
            await request.callback(
                **get_func_kwargs(
                    request.callback,
                    request=request,
                    response=response,
                    **request.cb_kwargs,
                    **self._dependencies,
                ),
            )

    async def _handle_exception(self, request: Request, exc: Exception):
        for exception_middleware in self._middleware_holder.exception:
            try:
                await exception_middleware(
                    **get_func_kwargs(exception_middleware, exc=exc, request=request, **self._dependencies),
                )
            except StopRequestProcessing:
                logger.debug(
                    "StopRequestProcessing in exception middleware for %s %s: aborting",
                    request.method,
                    request.url,
                )
                return
            except StopMiddlewareProcessing:
                logger.debug(
                    "StopMiddlewareProcessing in exception middleware for %s %s: stopping exception chain",
                    request.method,
                    request.url,
                )
                break

        if request.errback is not None:
            try:
                if hasattr(request.errback, "__compiled__"):
                    await request.errback(
                        request=request,
                        exc=exc,
                        **request.cb_kwargs,
                        **self._dependencies,
                    )
                else:
                    await request.errback(
                        **get_func_kwargs(
                            request.errback,
                            request=request,
                            exc=exc,
                            **request.cb_kwargs,
                            **self._dependencies,
                        ),
                    )
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
        """Process requests from the queue using the rate limiter."""
        while (
            not self._initialized
            or len(self._scheduler) > 0
            or self._rate_limiter_manager.active
            or not self._ready_queue.empty()
            or len(self._delayed_heap) > 0
            or await self._rate_limiter_manager.shutdown()
        ):
            await self._pop_due_delayed()

            timeout = self._next_timeout()
            try:
                pr = await asyncio.wait_for(self._ready_queue.get(), timeout)
            except asyncio.TimeoutError:
                continue

            try:
                await asyncio.shield(self._process_request(pr))
            except asyncio.CancelledError:
                logger.debug("Queue listener cancelled")
                break

        self._completed.set()
        logger.info("Queue listener completed: all requests processed")

    async def _process_request(self, pr: PRequest):
        for outer_middleware in self._middleware_holder.outer:
            try:
                await outer_middleware(**get_func_kwargs(outer_middleware, request=pr.request, **self._dependencies))
            except (StopMiddlewareProcessing, StopRequestProcessing) as e:
                logger.debug("%s in outer middleware is ignored", type(e).__name__)
            except Exception:
                logger.exception("Error when executed outer middleware %s", get_log_name(outer_middleware))

        await self._rate_limiter_manager(pr)

    async def _pop_due_delayed(self):
        """Pop the next due delayed request from the heap."""
        now = monotonic()
        while self._delayed_heap and self._delayed_heap[0].priority <= now:
            pr = heapq.heappop(self._delayed_heap)
            pr.request.delay = None
            await self._ready_queue.put(pr)

    def _next_timeout(self) -> float | None:
        if not self._delayed_heap:
            return 0.05

        pr = self._delayed_heap[0]
        timeout = pr.priority - monotonic()

        if timeout <= 0:
            return 0.0

        return timeout

    async def close(self):
        """Close the underlying session."""
        await execute_coroutines(self._rate_limiter_manager.close(), self._scheduler.close(), self._session.close())
        logger.debug("Request manager closed successfully")
