import asyncio
import heapq
from logging import getLogger
from time import monotonic
from typing import Any

from aiojobs import Scheduler

from aioscraper.config.models import RateLimitConfig, SchedulerConfig

from .rate_limiter import RateLimiterManager
from .session import SessionMaker
from ..exceptions import HTTPException, InvalidRequestData, StopMiddlewareProcessing, StopRequestProcessing
from .._helpers.asyncio import execute_coroutine, execute_coroutines
from .._helpers.func import get_func_kwargs
from .._helpers.http import parse_url
from ..types.session import Request, PRequest, SendRequest
from ..holders import MiddlewareHolder

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
        shutdown_check_interval (float): Interval between shutdown checks in seconds
        sessionmaker (SessionMaker): A factory for creating session objects.
        dependencies (dict[str, Any]): Additional dependencies to be injected into middleware and callbacks.
        middleware_holder (MiddlewareHolder): A container for middleware collections.
    """

    def __init__(
        self,
        scheduler_config: SchedulerConfig,
        rate_limit_config: RateLimitConfig,
        shutdown_check_interval: float,
        sessionmaker: SessionMaker,
        dependencies: dict[str, Any],
        middleware_holder: MiddlewareHolder,
    ):
        self._scheduler = Scheduler(
            limit=scheduler_config.concurrent_requests,
            pending_limit=scheduler_config.pending_requests,
            close_timeout=scheduler_config.close_timeout,
        )
        self._shutdown_check_interval = shutdown_check_interval
        self._session = sessionmaker()
        self._ready_queue: _RequestQueue = asyncio.PriorityQueue()
        self._delayed_heap: _RequestHead = []
        self._request_sender = _get_request_sender(self._ready_queue, self._delayed_heap)
        self._dependencies: dict[str, Any] = {"send_request": self._request_sender, **dependencies}
        self._middleware_holder = middleware_holder
        self._rate_limiter_manager = RateLimiterManager(
            rate_limit_config,
            schedule=lambda pr: self._scheduler.spawn(execute_coroutine(self._send_request(pr.request))),
        )
        self._wait = True
        self._completed = False
        self._task = asyncio.create_task(self._listen_queue())

    @property
    def sender(self) -> SendRequest:
        return self._request_sender

    async def _send_request(self, request: Request):
        try:
            for inner_middleware in self._middleware_holder.inner:
                try:
                    await inner_middleware(**get_func_kwargs(inner_middleware, request=request, **self._dependencies))
                except StopRequestProcessing:
                    logger.debug("StopRequestProcessing in inner middleware: aborting request processing")
                    return
                except StopMiddlewareProcessing:
                    logger.debug("StopMiddlewareProcessing in inner middleware: stopping inner chain")
                    break

            url = parse_url(request.url, request.params)
            logger.debug(f"send request: {request.method} {url}")

            async with self._session.make_request(request) as response:
                for response_middleware in self._middleware_holder.response:
                    try:
                        await response_middleware(
                            **get_func_kwargs(
                                response_middleware,
                                request=request,
                                response=response,
                                **self._dependencies,
                            )
                        )
                    except StopRequestProcessing:
                        logger.debug("StopRequestProcessing in response middleware: aborting request processing")
                        return
                    except StopMiddlewareProcessing:
                        logger.debug("StopMiddlewareProcessing in response middleware: stopping response chain")
                        break

                if response.ok or not request.raise_for_status:
                    if request.callback is not None:
                        await request.callback(
                            **get_func_kwargs(
                                request.callback,
                                request=request,
                                response=response,
                                **request.cb_kwargs,
                                **self._dependencies,
                            ),
                        )
                else:
                    await self._handle_exception(
                        request,
                        exc=HTTPException(
                            url=str(url),
                            method=response.method,
                            headers=response.headers,
                            status_code=response.status,
                            message=await response.text(errors="replace"),
                        ),
                    )
        except Exception as exc:
            await self._handle_exception(request, exc)

    async def _handle_exception(self, request: Request, exc: Exception):
        for exception_middleware in self._middleware_holder.exception:
            try:
                await exception_middleware(
                    **get_func_kwargs(exception_middleware, exc=exc, request=request, **self._dependencies)
                )
            except StopRequestProcessing:
                logger.debug("StopRequestProcessing in exception middleware: aborting request processing")
                return
            except StopMiddlewareProcessing:
                logger.debug("StopMiddlewareProcessing in exception middleware: stopping exception chain")
                break

        if request.errback is not None:
            try:
                await request.errback(
                    **get_func_kwargs(
                        request.errback,
                        request=request,
                        exc=exc,
                        **request.cb_kwargs,
                        **self._dependencies,
                    )
                )
            except Exception as errback_exc:
                raise ExceptionGroup("Errback failed", [exc, errback_exc])
        else:
            logger.error(f"{request.method}: {request.url}: {exc}", exc_info=exc)

    async def wait(self):
        self._wait = False
        while not self._completed:
            await asyncio.sleep(self._shutdown_check_interval)

    async def shutdown(self):
        await self._task

    async def _listen_queue(self):
        """Process requests from the queue using the rate limiter."""
        while (
            len(self._scheduler) > 0
            or self._rate_limiter_manager.active
            or not self._ready_queue.empty()
            or len(self._delayed_heap) > 0
            or self._wait
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
                break

        self._completed = True

    async def _process_request(self, pr: PRequest):
        for outer_middleware in self._middleware_holder.outer:
            try:
                await outer_middleware(**get_func_kwargs(outer_middleware, request=pr.request, **self._dependencies))
            except (StopMiddlewareProcessing, StopRequestProcessing) as e:
                logger.debug(f"{type(e).__name__} in outer middleware is ignored")
            except Exception as e:
                logger.error(f"Error when executed outer middleware {outer_middleware.__name__}: {e}", exc_info=e)

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
