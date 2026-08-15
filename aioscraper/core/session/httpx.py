from ssl import SSLContext

from httpx import USE_CLIENT_DEFAULT, AsyncClient, AsyncHTTPTransport, BasicAuth

from aioscraper._helpers.http import parse_cookies, parse_url, to_simple_cookie
from aioscraper.exceptions import UnsupportedRequestOption
from aioscraper.types import Request, Response
from aioscraper.types.session import DEFAULT_MAX_REDIRECTS

from .base import BaseRequestContextManager, BaseSession

_BACKEND = "httpx"

# httpx resolves proxies per transport and redirect limits per client, so none of these
# can vary per request without building a client for every request.
_UNSUPPORTED_HINTS = {
    "proxy": "Set SessionConfig.proxy, or use the aiohttp backend.",
    "proxy_auth": "Embed the credentials in the SessionConfig.proxy URL, or use the aiohttp backend.",
    "proxy_headers": "Use the aiohttp backend.",
}


def _check_supported(request: Request):
    """Reject request options httpx cannot honor, instead of dropping them silently.

    Args:
        request (Request): The request about to be sent.

    Raises:
        UnsupportedRequestOption: One of the options is set and cannot be applied.
    """
    for option, hint in _UNSUPPORTED_HINTS.items():
        if getattr(request, option) is not None:
            raise UnsupportedRequestOption(_BACKEND, option, hint)

    if request.allow_redirects and request.max_redirects != DEFAULT_MAX_REDIRECTS:
        raise UnsupportedRequestOption(
            _BACKEND,
            "max_redirects",
            f"The limit is fixed at {DEFAULT_MAX_REDIRECTS}. Use the aiohttp backend for a per-request value.",
        )


class HttpxRequestContextManager(BaseRequestContextManager):
    """httpx-backed context manager that executes a prepared HTTP request."""

    def __init__(self, request: Request, client: AsyncClient, max_body_size: int | None = None):
        super().__init__(request)
        self._client = client
        self._max_body_size = max_body_size

    async def __aenter__(self) -> Response:
        """Send the request with httpx and convert the response to internal ``Response``."""
        if isinstance(self._request.data, dict):
            content, data = None, self._request.data
        else:
            content, data = self._request.data, None

        request = self._client.build_request(
            url=str(parse_url(self._request.url, self._request.params)),
            method=self._request.method,
            content=content,
            data=data,
            files=self._request.files,
            json=self._request.json_data,
            cookies=parse_cookies(self._request.cookies) if self._request.cookies is not None else None,
            headers=self._request.headers,
            timeout=self._request.timeout or USE_CLIENT_DEFAULT,
        )
        # without stream=True httpx buffers the whole body inside send(), before any limit applies
        response = await self._client.send(
            request,
            auth=(
                BasicAuth(username=self._request.auth["username"], password=self._request.auth.get("password", ""))
                if self._request.auth is not None
                else USE_CLIENT_DEFAULT
            ),
            follow_redirects=self._request.allow_redirects,
            stream=True,
        )
        self._exit_stack.push_async_callback(response.aclose)
        return Response(
            url=str(response.url),
            method=response.request.method,
            status=response.status_code,
            headers=response.headers,
            cookies=to_simple_cookie(response.cookies),
            aiter_bytes=response.aiter_bytes,
            max_body_size=self._max_body_size,
        )


class HttpxSession(BaseSession):
    """HTTP session implementation that wraps an :class:`httpx.AsyncClient`."""

    def __init__(
        self,
        timeout: float | None,
        verify: SSLContext | bool,
        proxy: str | dict[str, str | None] | None,
        max_body_size: int | None = None,
    ):
        """Instantiate an ``AsyncClient`` honoring timeout/SSL/proxy configuration."""
        self._max_body_size = max_body_size
        if isinstance(proxy, dict):
            mounts = {scheme: AsyncHTTPTransport(proxy=proxy) for scheme, proxy in proxy.items() if proxy} or None
            proxy = None
        else:
            mounts = None

        # Pinned to the Request default so both backends follow the same number of
        # redirects; httpx would otherwise use its own default of 20.
        self._client = AsyncClient(
            timeout=timeout,
            verify=verify,
            proxy=proxy,
            mounts=mounts,
            max_redirects=DEFAULT_MAX_REDIRECTS,
        )

    def make_request(self, request: Request) -> HttpxRequestContextManager:
        """Create a request context manager coupled with the shared client.

        Args:
            request (Request): The request to execute.

        Raises:
            UnsupportedRequestOption: The request sets an option httpx cannot honor per request.
        """
        _check_supported(request)
        return HttpxRequestContextManager(request, self._client, self._max_body_size)

    async def close(self):
        """Close the ``AsyncClient`` to free connectors and sockets."""
        await self._client.aclose()
