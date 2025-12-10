import abc
from contextlib import AsyncExitStack
from types import TracebackType

from aioscraper.types import Request, Response


class BaseRequestContextManager(abc.ABC):
    """Asynchronous context manager that encapsulates request execution lifecycle."""

    def __init__(self, request: Request):
        self._request = request
        self._exit_stack = AsyncExitStack()

    @abc.abstractmethod
    async def __aenter__(self) -> Response:
        """Send the HTTP request and return a populated :class:`Response`."""

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ):
        """Tear down resources registered in the exit stack when the request finishes."""
        await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)


class BaseSession(abc.ABC):
    "Base abstract class for HTTP session."

    @abc.abstractmethod
    def make_request(self, request: Request) -> BaseRequestContextManager:
        """Build a context manager responsible for executing ``request``."""
        ...

    @abc.abstractmethod
    async def close(self):
        """
        Close the session and release all resources.

        This method should be called after finishing work with the session
        to properly release resources.
        """
        ...
