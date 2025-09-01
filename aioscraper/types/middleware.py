from typing import Protocol, TypeVar

from .session import Request, RequestParams, Response


class RequestMiddleware(Protocol):
    """
    Protocol defining the interface for request middleware.

    A request middleware is a callable that can intercept and modify requests before they are sent.
    It receives the request and parameters as input and can modify them in place.

    Args:
        request (Request): The request object to be processed
        params (RequestParams): The parameters associated with the request
    """

    async def __call__(self, request: Request, params: RequestParams) -> None: ...


class RequestExceptionMiddleware(Protocol):
    """
    Protocol defining the interface for request exception middleware.

    A request exception middleware is a callable that can handle exceptions
    that occur during a request. It receives the original request, parameters,
    and the exception as input for processing.

    Args:
        request (Request): The original request object that caused the exception.
        params (RequestParams): The parameters associated with the request.
        exc (Exception): The exception object that was raised.

    Returns:
        bool | None: If `True` is returned, it indicates that the exception
        has been handled, and any subsequent exception middleware (and the
        request's `errback`) will be skipped. If `None` is returned,
        processing continues to the next exception middleware or the
        request's `errback`.
    """

    async def __call__(self, request: Request, params: RequestParams, exc: Exception) -> bool | None: ...


class ResponseMiddleware(Protocol):
    """
    Protocol defining the interface for response middleware.

    A response middleware is a callable that can process responses after they are received.
    It receives the response and original request parameters as input for processing.

    Args:
        params (RequestParams): The original parameters used for the request
        response (Response): The response object to be processed
    """

    async def __call__(self, params: RequestParams, response: Response) -> None: ...


MiddlewareType = TypeVar("MiddlewareType", RequestMiddleware, RequestExceptionMiddleware, ResponseMiddleware)
