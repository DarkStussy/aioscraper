from typing import Callable, Protocol

from .session import Request, Response


class RequestHandler(Protocol):
    """The ``call_next`` a middleware is handed: the rest of the chain, down to the HTTP dispatch.

    Returns the response, or ``None`` when a middleware below handled the request itself and the
    callback is to be skipped. Raises what dispatch or a middleware raised, which reaches the
    errback unless the retry policy takes the request back first.
    """

    async def __call__(self, request: Request) -> Response | None: ...


class RequestMiddleware(Protocol):
    """One layer around the request dispatch.

    Change the request before awaiting ``call_next``, look at the response after, catch what it
    raises, or skip it entirely. Returning ``None`` says the request was handled here: neither the
    callback nor the errback runs for that attempt.
    """

    async def __call__(
        self,
        call_next: RequestHandler,
        request: Request,
    ) -> Response | None: ...


RequestMiddlewareFactory = Callable[..., RequestMiddleware]
