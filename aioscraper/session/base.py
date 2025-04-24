import abc

from ..types import Request, Response


class BaseSession(abc.ABC):
    "Base abstract class for HTTP session"

    def __init__(self, timeout: float | None = None, ssl: bool | None = None) -> None:
        self._timeout = timeout
        self._ssl = ssl

    @abc.abstractmethod
    async def make_request(self, request: Request) -> Response:
        """
        Execute an HTTP request.

        Args:
            request (Request): Request object containing all necessary parameters.

        Returns:
            Response: Response object containing the result of the request execution.
        """
        ...

    async def close(self) -> None:
        """
        Close the session and release all resources.

        This method should be called after finishing work with the session
        to properly release resources.
        """
        ...
