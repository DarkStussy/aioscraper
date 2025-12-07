import asyncio
import sys
from logging import getLogger
from typing import Callable, Awaitable, Any
from typing import Coroutine

from aioscraper.config.models import RateLimitConfig

from .rate_limiter import RateLimiterManager
from .session import SessionMaker
from ..exceptions import HTTPException, InvalidRequestData, StopMiddlewareProcessing, StopRequestProcessing
from .._helpers.asyncio import execute_coroutine
from .._helpers.func import get_func_kwargs
from .._helpers.http import parse_url
from ..types.session import Request, PRequest, SendRequest
from ..holders import MiddlewareHolder

logger = getLogger(__name__)


_RequestQueue = asyncio.PriorityQueue[PRequest]


def _get_request_sender(queue: _RequestQueue) -> SendRequest:
    "Creates a request sender function that adds requests to the priority queue."

    async def sender(request: Request) -> Request:
        if request.json_data is not None and request.data is not None:
            raise InvalidRequestData("Cannot send both data and json_data")

        if request.json_data is not None and request.files is not None:
            raise InvalidRequestData("Cannot send both files and json_data")

        await queue.put(PRequest(priority=request.priority, request=request))
        return request

    return sender


class RequestManager:
    """
    Manages HTTP requests with priority queuing, rate limiting, and middleware support.

    Args:
        rate_limit_config (RateLimitConfig): Configuration for the request rate limiter.
        sessionmaker (SessionMaker): A factory for creating session objects.
        schedule (Callable[[Coroutine[Any, Any, None]], Awaitable[Any]]): Function to schedule request processing.
        queue (_RequestQueue): Priority queue for requests.
        dependencies (dict[str, Any]): Additional dependencies to be injected into middleware and callbacks.
        middleware_holder (MiddlewareHolder): A container for middleware collections.
    """

    def __init__(
        self,
        rate_limit_config: RateLimitConfig,
        sessionmaker: SessionMaker,
        schedule: Callable[[Coroutine[Any, Any, None]], Awaitable[Any]],
        queue: _RequestQueue,
        dependencies: dict[str, Any],
        middleware_holder: MiddlewareHolder,
    ):
        self._session = sessionmaker()
        self._schedule = schedule
        self._queue = queue
        self._request_sender = _get_request_sender(queue)
        self._dependencies: dict[str, Any] = {"send_request": self._request_sender, **dependencies}
        self._middleware_holder = middleware_holder
        self._rate_limiter_manager = RateLimiterManager(
            rate_limit_config,
            schedule=lambda pr: self._schedule(execute_coroutine(self._send_request(pr.request))),
        )
        self._closed = False
        self._task: asyncio.Task[None] | None = None

    @property
    def sender(self) -> SendRequest:
        return self._request_sender

    @property
    def active(self) -> bool:
        return self._rate_limiter_manager.active or not self._queue.empty()

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

    def listen_queue(self):
        """Start listening to the request queue."""
        self._task = asyncio.create_task(self._listen_queue())

    async def _listen_queue(self):
        """Process requests from the queue using the rate limiter."""
        while True:
            pr = await self._queue.get()

            if self._closed:
                break

            for outer_middleware in self._middleware_holder.outer:
                try:
                    await outer_middleware(
                        **get_func_kwargs(outer_middleware, request=pr.request, **self._dependencies)
                    )
                except (StopMiddlewareProcessing, StopRequestProcessing) as e:
                    logger.debug(f"{type(e).__name__} in outer middleware is ignored")
                except Exception as e:
                    logger.error(f"Error when executed outer middleware {outer_middleware.__name__}: {e}", exc_info=e)

            await self._rate_limiter_manager(pr)

    async def close(self):
        """Close the underlying session."""
        self._closed = True
        await self._queue.put(PRequest(priority=sys.maxsize, request=Request(url="stub")))

        if self._task is not None:
            await self._task

        await self._rate_limiter_manager.close()
        await self._session.close()
