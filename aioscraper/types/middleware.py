from typing import Callable, Protocol

from .session import Request, Response


class RequestHandler(Protocol):
    """Callable that processes a request through the middleware chain.

    Returns the response on success. Returns ``None`` when the chain handled
    the request internally (e.g. retry scheduled) and the orchestrator should
    skip the callback. Raises to route the failure to the request errback.
    """

    async def __call__(self, request: Request) -> Response | None: ...


class RequestMiddleware(Protocol):
    """Async middleware wrapping the request handler chain.

    Implementations may modify the request before invoking ``call_next``,
    short-circuit by not calling it, inspect the returned response, or catch
    exceptions. Return ``None`` to signal that the request was handled
    internally and the orchestrator should skip the callback.
    """

    async def __call__(
        self,
        call_next: RequestHandler,
        request: Request,
    ) -> Response | None: ...


RequestMiddlewareFactory = Callable[..., RequestMiddleware]
