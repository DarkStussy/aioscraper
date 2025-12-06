import abc

from ..types import Request, Response


class BaseSession(abc.ABC):
    "Base abstract class for HTTP session."

    @abc.abstractmethod
    async def make_request(self, request: Request) -> Response:
        """
        Execute an HTTP request.

        Args:
            request (Request): Request object containing all necessary parameters

        Returns:
            Response: Response object containing the result of the request execution
        """
        ...

    async def close(self):
        """
        Close the session and release all resources.

        This method should be called after finishing work with the session
        to properly release resources.
        """
        ...
