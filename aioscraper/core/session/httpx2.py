import httpx2
from httpx2 import USE_CLIENT_DEFAULT, AsyncClient, AsyncHTTPTransport, BasicAuth

from ._httpx import BaseHttpxRequestContextManager, BaseHttpxSession, HttpxBinding, make_classifier

_BINDING = HttpxBinding(
    backend="httpx2",
    async_client=AsyncClient,
    async_http_transport=AsyncHTTPTransport,
    basic_auth=BasicAuth,
    use_client_default=USE_CLIENT_DEFAULT,
    classify=make_classifier(httpx2),
)


class Httpx2RequestContextManager(BaseHttpxRequestContextManager):
    "Sends one request with ``httpx2``, translating its failures on the way out."

    _binding = _BINDING


class Httpx2Session(BaseHttpxSession):
    "HTTP session implementation that wraps an :class:`httpx2.AsyncClient`."

    _binding = _BINDING
    _context_manager = Httpx2RequestContextManager
