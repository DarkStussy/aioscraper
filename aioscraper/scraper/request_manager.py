import asyncio
import sys
from dataclasses import dataclass, field
from logging import getLogger
from typing import Callable, Awaitable, Any
from typing import Coroutine

from ..exceptions import HTTPException, StopMiddlewareProcessing, StopRequestProcessing
from .._helpers.asyncio import execute_coroutine
from .._helpers.func import get_func_kwargs
from .._helpers.http import parse_url
from ..session import BaseSession
from ..types import Request, SendRequest
from ..holders import MiddlewareHolder

logger = getLogger(__name__)


@dataclass(slots=True, order=True)
class _PRequest:
    "Priority Request Pair - Internal class for managing prioritized requests."

    priority: int
    request: Request = field(compare=False)


_RequestQueue = asyncio.PriorityQueue[_PRequest]


def _get_request_sender(queue: _RequestQueue) -> SendRequest:
    "Creates a request sender function that adds requests to the priority queue."

    async def sender(request: Request) -> Request:
        await queue.put(_PRequest(priority=request.priority, request=request))
        return request

    return sender


class RequestManager:
    """
    Manages HTTP requests with priority queuing and middleware support.

    Args:
        session (BaseSession): HTTP session
        schedule_request (Callable[[Coroutine], Awaitable]): Function to schedule request processing
        queue (_RequestQueue): Priority queue for requests
        delay (float): Delay between requests in seconds
        shutdown_timeout (float): Timeout for graceful shutdown
        dependencies (dict[str, Any]): Additional dependencies to request
        middleware_holder (MiddlewareHolder): Buckets of outer/inner/exception/response middlewares
    """

    def __init__(
        self,
        session: BaseSession,
        schedule_request: Callable[[Coroutine[Any, Any, None]], Awaitable[Any]],
        queue: _RequestQueue,
        delay: float,
        shutdown_timeout: float,
        dependencies: dict[str, Any],
        middleware_holder: MiddlewareHolder,
    ) -> None:
        self._session = session
        self._schedule_request = schedule_request
        self._queue = queue
        self._delay = delay
        self._shutdown_timeout = shutdown_timeout
        self._request_sender = _get_request_sender(queue)
        self._dependencies: dict[str, Any] = {"send_request": self._request_sender, **dependencies}
        self._middleware_holder = middleware_holder
        self._event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def sender(self) -> SendRequest:
        return self._request_sender

    async def _send_request(self, request: Request) -> None:
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

            response = await self._session.make_request(request)

            for response_middleware in self._middleware_holder.response:
                try:
                    await response_middleware(
                        **get_func_kwargs(response_middleware, request=request, response=response, **self._dependencies)
                    )
                except StopRequestProcessing:
                    logger.debug("StopRequestProcessing in response middleware: aborting request processing")
                    return
                except StopMiddlewareProcessing:
                    logger.debug("StopMiddlewareProcessing in response middleware: stopping response chain")
                    break

            if response.status >= 400:
                await self._handle_exception(
                    request,
                    exc=HTTPException(
                        status_code=response.status,
                        message=response.text(errors="replace"),
                        url=str(url),
                        method=response.method,
                        content=response.content,
                    ),
                )
            elif request.callback is not None:
                await request.callback(
                    **get_func_kwargs(
                        request.callback,
                        request=request,
                        response=response,
                        **request.cb_kwargs,
                        **self._dependencies,
                    ),
                )
        except Exception as exc:
            await self._handle_exception(request, exc)

    async def _handle_exception(self, request: Request, exc: Exception) -> None:
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

    def listen_queue(self) -> None:
        """Start listening to the request queue."""
        self._task = asyncio.create_task(self._listen_queue())

    async def _listen_queue(self) -> None:
        """Process requests from the queue with configured delay."""
        while True:
            r = await self._queue.get()

            if self._event.is_set():
                break

            for outer_middleware in self._middleware_holder.outer:
                try:
                    await outer_middleware(**get_func_kwargs(outer_middleware, request=r.request, **self._dependencies))
                except (StopMiddlewareProcessing, StopRequestProcessing) as e:
                    logger.debug(f"{e.__class__.__name__} in outer middleware is ignored")
                except Exception as e:
                    logger.error(f"Error when executed outer middleware {outer_middleware.__name__}: {e}", exc_info=e)

            await self._schedule_request(execute_coroutine(self._send_request(r.request)))
            await asyncio.sleep(self._delay)

    async def close(self) -> None:
        """Close the underlying session."""
        self._event.set()
        await self._queue.put(_PRequest(priority=sys.maxsize, request=Request(url="stub")))

        if self._task is not None:
            await self._task

        await self._session.close()
