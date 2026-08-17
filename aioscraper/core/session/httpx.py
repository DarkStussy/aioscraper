from httpx import USE_CLIENT_DEFAULT, AsyncClient, AsyncHTTPTransport, BasicAuth

from ._httpx import BaseHttpxRequestContextManager, BaseHttpxSession, HttpxBinding

_BINDING = HttpxBinding(
    backend="httpx",
    async_client=AsyncClient,
    async_http_transport=AsyncHTTPTransport,
    basic_auth=BasicAuth,
    use_client_default=USE_CLIENT_DEFAULT,
)


class HttpxRequestContextManager(BaseHttpxRequestContextManager):
    """httpx-backed context manager that executes a prepared HTTP request."""

    _binding = _BINDING


class HttpxSession(BaseHttpxSession):
    "HTTP session implementation that wraps an :class:`httpx.AsyncClient`."

    _binding = _BINDING
    _context_manager = HttpxRequestContextManager
