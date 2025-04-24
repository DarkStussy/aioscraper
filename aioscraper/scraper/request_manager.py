import asyncio
from dataclasses import dataclass, field
from logging import Logger
from typing import Callable, Awaitable, Any
from typing import Coroutine

from ..exceptions import HTTPException, RequestException, ClientException
from ..helpers import get_cb_kwargs
from ..session.base import BaseSession
from ..types import (
    QueryParams,
    Cookies,
    Headers,
    BasicAuth,
    Request,
    RequestParams,
    RequestMiddleware,
    ResponseMiddleware,
    RequestSender,
)


@dataclass(slots=True, order=True)
class _PRPRequest:
    "Priority Request Pair - Internal class for managing prioritized requests"

    priority: int
    request: Request = field(compare=False)
    request_params: RequestParams = field(compare=False)


_RequestQueue = asyncio.PriorityQueue[_PRPRequest | None]


def _get_request_sender(queue: _RequestQueue) -> RequestSender:
    "Creates a request sender function that adds requests to the priority queue"

    async def sender(
        url: str,
        method: str = "GET",
        callback: Callable[..., Awaitable] | None = None,
        cb_kwargs: dict[str, Any] | None = None,
        errback: Callable[..., Awaitable] | None = None,
        params: QueryParams | None = None,
        data: Any = None,
        json_data: Any = None,
        cookies: Cookies | None = None,
        headers: Headers | None = None,
        proxy: str | None = None,
        auth: BasicAuth | None = None,
        timeout: float | None = None,
        priority: int = 0,
    ) -> None:
        await queue.put(
            _PRPRequest(
                priority=priority,
                request=Request(
                    method=method,
                    url=url,
                    params=params,
                    data=data,
                    json_data=json_data,
                    cookies=cookies,
                    headers=headers,
                    auth=auth,
                    proxy=proxy,
                    timeout=timeout,
                ),
                request_params=RequestParams(
                    callback=callback,
                    cb_kwargs=cb_kwargs,
                    errback=errback,
                ),
            )
        )

    return sender


class RequestManager:
    """
    Manages HTTP requests with priority queuing and middleware support.

    Attributes:
        logger (Logger): Logger instance.
        session (BaseSession): HTTP session.
        schedule_request (Callable[[Coroutine], Awaitable]): Function to schedule request processing.
        queue (_RequestQueue): Priority queue for requests.
        delay (float): Delay between requests in seconds.
        shutdown_timeout (float): Timeout for graceful shutdown.
        srv_kwargs (dict): Additional service arguments.
        request_outer_middlewares (list[RequestMiddleware]): Middleware to run before queue processing.
        request_inner_middlewares (list[RequestMiddleware]): Middleware to run before request execution.
        response_middlewares (list[ResponseMiddleware]): Middleware to run after response received.
    """

    def __init__(
        self,
        logger: Logger,
        session: BaseSession,
        schedule_request: Callable[[Coroutine], Awaitable],
        queue: _RequestQueue,
        delay: float,
        shutdown_timeout: float,
        srv_kwargs: dict[str, Any],
        request_outer_middlewares: list[RequestMiddleware],
        request_inner_middlewares: list[RequestMiddleware],
        response_middlewares: list[ResponseMiddleware],
    ) -> None:
        self._logger = logger
        self._session = session
        self._schedule_request = schedule_request
        self._queue = queue
        self._delay = delay
        self._shutdown_timeout = shutdown_timeout
        self._request_sender = _get_request_sender(queue)
        self._srv_kwargs = {"send_request": self._request_sender, **srv_kwargs}
        self._request_outer_middlewares = request_outer_middlewares
        self._request_inner_middlewares = request_inner_middlewares
        self._response_middlewares = response_middlewares
        self._task: asyncio.Task | None = None

    @property
    def sender(self) -> RequestSender:
        "Get the request sender function"
        return self._request_sender

    async def _send_request(self, request: Request, params: RequestParams) -> None:
        full_url = request.full_url
        self._logger.debug(f"request: {request.method} {full_url}")
        try:
            for inner_middleware in self._request_inner_middlewares:
                await inner_middleware(request, params)

            response = await self._session.make_request(request)
            for response_middleware in self._response_middlewares:
                await response_middleware(params, response)

            if response.status >= 400:
                await self._handle_client_exception(
                    params,
                    client_exc=HTTPException(
                        status_code=response.status,
                        message=response.text(),
                        url=full_url,
                        method=response.method,
                    ),
                )
            elif params.callback is not None:
                await params.callback(
                    response,
                    **get_cb_kwargs(params.callback, srv_kwargs=self._srv_kwargs, cb_kwargs=params.cb_kwargs),
                )
        except Exception as exc:
            await self._handle_client_exception(
                params,
                client_exc=RequestException(src=exc, url=full_url, method=request.method),
            )

    async def _handle_client_exception(self, params: RequestParams, client_exc: ClientException) -> None:
        if params.errback is None:
            raise client_exc

        try:
            await params.errback(
                client_exc,
                **get_cb_kwargs(params.errback, srv_kwargs=self._srv_kwargs, cb_kwargs=params.cb_kwargs),
            )
        except Exception as exc:
            self._logger.exception(exc)

    def listen_queue(self) -> None:
        """Start listening to the request queue."""
        self._task = asyncio.create_task(self._listen_queue())

    async def _listen_queue(self) -> None:
        """Process requests from the queue with configured delay."""
        while (r := (await self._queue.get())) is not None:
            for outer_middleware in self._request_outer_middlewares:
                await outer_middleware(r.request, r.request_params)

            await self._schedule_request(self._send_request(r.request, r.request_params))
            await asyncio.sleep(self._delay)

    async def shutdown(self, force: bool = False) -> None:
        """
        Shutdown the request manager.

        Args:
            force (bool): If True, force shutdown after timeout
        """
        await self._queue.put(None)
        if self._task is not None:
            await asyncio.wait_for(self._task, timeout=self._shutdown_timeout) if force else await self._task

    async def close(self) -> None:
        """Close the underlying session."""
        await self._session.close()
