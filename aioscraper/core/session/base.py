import abc
from contextlib import AsyncExitStack
from types import TracebackType

from aioscraper.types import Request, Response


def resolve_client_ownership(client: object | None, owns_client: bool | None) -> bool:
    """Decide who closes the client a session is built with.

    Args:
        client (object | None): The client passed in, or ``None`` when the session creates one.
        owns_client (bool | None): The caller's explicit choice, if any.

    Returns:
        bool: Whether the session closes the client. Defaults to ``True`` for a client it creates
        and ``False`` for one it is given.

    Raises:
        ValueError: Ownership of a client the session creates is declined. A session never exposes
            that client, so nothing else could close it.
    """
    if client is None:
        if owns_client is False:
            raise ValueError("owns_client=False needs a client to disown")

        return True

    return owns_client if owns_client is not None else False


class BaseRequestContextManager(abc.ABC):
    """One request, from dispatch to the connection being released.

    Entering it sends the request and returns a :class:`Response` whose body is still on the
    connection; leaving it releases the connection, so the body has to be read in between.
    """

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
        """Release the connection and anything else the send registered."""
        await self._exit_stack.__aexit__(exc_type, exc_val, exc_tb)


class BaseSession(abc.ABC):
    """The HTTP client of a run, shared by every request it sends.

    Args:
        owns_client (bool): Whether the session created the underlying HTTP client and is
            therefore the one to close it. A subclass that skips this constructor owns its client.
    """

    _owns_client = True

    def __init__(self, *, owns_client: bool = True):
        self._owns_client = owns_client

    @property
    def owns_client(self) -> bool:
        "Whether :meth:`close` closes the underlying HTTP client."
        return self._owns_client

    @abc.abstractmethod
    def make_request(self, request: Request) -> BaseRequestContextManager:
        """Prepare ``request`` for sending; nothing is sent until the result is entered."""
        ...

    @abc.abstractmethod
    async def _close_client(self):
        """Close the underlying HTTP client."""
        ...

    async def close(self):
        "Close the client, unless it belongs to the caller, in which case it is left open."
        if self._owns_client:
            await self._close_client()
