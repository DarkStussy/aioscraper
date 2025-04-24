from typing import Protocol

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
