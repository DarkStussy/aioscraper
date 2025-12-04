import asyncio
import sys
from dataclasses import dataclass, field
from logging import getLogger
from typing import Callable, Awaitable, Any
from typing import Coroutine


from ..exceptions import HTTPException, StopMiddlewareProcessing
from .._helpers.asyncio import execute_coroutine
from .._helpers.func import get_func_kwargs
from .._helpers.http import parse_url
from ..session import BaseSession
from ..types import Request, Middleware, SendRequest

logger = getLogger(__name__)


@dataclass(slots=True, order=True)
class _PRequest:
    "Priority Request Pair - Internal class for managing prioritized requests."

    priority: int
    request: Request | None = field(compare=False)


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
        dependencies (dict): Additional dependencies to request
        request_outer_middlewares (list[RequestMiddleware]): Middleware to run before queue processing
        request_inner_middlewares (list[RequestMiddleware]): Middleware to run before request execution
        response_middlewares (list[ResponseMiddleware]): Middleware to run after response received
    """

    def __init__(
        self,
        session: BaseSession,
        schedule_request: Callable[[Coroutine[Any, Any, None]], Awaitable[Any]],
        queue: _RequestQueue,
        delay: float,
        shutdown_timeout: float,
        dependencies: dict[str, Any],
        request_outer_middlewares: list[Middleware],
        request_inner_middlewares: list[Middleware],
        request_exception_middlewares: list[Middleware],
        response_middlewares: list[Middleware],
    ) -> None:
        self._session = session
        self._schedule_request = schedule_request
        self._queue = queue
        self._delay = delay
        self._shutdown_timeout = shutdown_timeout
        self._request_sender = _get_request_sender(queue)
        self._dependencies: dict[str, Any] = {"send_request": self._request_sender, **dependencies}
        self._request_outer_middlewares = request_outer_middlewares
        self._request_inner_middlewares = request_inner_middlewares
        self._request_exception_middlewares = request_exception_middlewares
        self._response_middlewares = response_middlewares
        self._task: asyncio.Task[None] | None = None

    @property
    def sender(self) -> SendRequest:
        return self._request_sender

    async def _send_request(self, request: Request) -> None:
        try:
            for inner_middleware in self._request_inner_middlewares:
                await inner_middleware(**get_func_kwargs(inner_middleware, request=request, **self._dependencies))

            url = parse_url(request.url, request.params)
            logger.debug(f"send request: {request.method} {url}")

            response = await self._session.make_request(request)

            for response_middleware in self._response_middlewares:
                await response_middleware(
                    **get_func_kwargs(response_middleware, request=request, response=response, **self._dependencies)
                )

            if response.status >= 400:
                await self._handle_exception(
                    request,
                    exc=HTTPException(
                        status_code=response.status,
                        message=response.text(),
                        url=str(url),
                        method=response.method,
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
        for exception_middleware in self._request_exception_middlewares:
            try:
                await exception_middleware(
                    **get_func_kwargs(exception_middleware, exc=exc, request=request, **self._dependencies)
                )
            except StopMiddlewareProcessing:
                return

        if request.errback is None:
            raise exc

        try:
            await request.errback(
                **get_func_kwargs(
                    request.errback,
                    request=request,
                    exc=exc,
                    **request.cb_kwargs,
                    **self._dependencies,
                ),
            )
        except Exception as exc:
            logger.exception(exc)

    def listen_queue(self) -> None:
        """Start listening to the request queue."""
        self._task = asyncio.create_task(self._listen_queue())

    async def _listen_queue(self) -> None:
        """Process requests from the queue with configured delay."""
        while True:
            r = await self._queue.get()
            if r.request is None:
                if r.priority == sys.maxsize:
                    logger.info("shutdown request manager")
                    break

                continue

            for outer_middleware in self._request_outer_middlewares:
                try:
                    await outer_middleware(**get_func_kwargs(outer_middleware, request=r.request, **self._dependencies))
                except Exception as e:
                    logger.error(f"Error when executed outer middleware {outer_middleware.__name__}: {e}", exc_info=e)

            await self._schedule_request(execute_coroutine(self._send_request(r.request)))
            await asyncio.sleep(self._delay)

    async def shutdown(self, force: bool = False) -> None:
        """
        Shutdown the request manager.

        Args:
            force (bool): If True, force shutdown after timeout
        """
        await self._queue.put(_PRequest(priority=sys.maxsize, request=None))
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=self._shutdown_timeout) if force else await self._task
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

    async def close(self) -> None:
        """Close the underlying session."""
        await self._session.close()
