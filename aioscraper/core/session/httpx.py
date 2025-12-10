from ssl import SSLContext

from httpx import USE_CLIENT_DEFAULT, AsyncClient, AsyncHTTPTransport, BasicAuth

from aioscraper._helpers.http import parse_cookies, parse_url, to_simple_cookie
from aioscraper.types import Request, Response

from .base import BaseRequestContextManager, BaseSession


class HttpxRequestContextManager(BaseRequestContextManager):
    """httpx-backed context manager that executes a prepared HTTP request."""

    def __init__(self, request: Request, client: AsyncClient):
        super().__init__(request)
        self._client = client

    async def __aenter__(self) -> Response:
        """Send the request with httpx and convert the response to internal ``Response``."""
        if isinstance(self._request.data, dict):
            content, data = None, self._request.data
        else:
            content, data = self._request.data, None

        response = await self._client.request(
            url=str(parse_url(self._request.url, self._request.params)),
            method=self._request.method,
            content=content,
            data=data,
            files=self._request.files,
            json=self._request.json_data,
            cookies=parse_cookies(self._request.cookies) if self._request.cookies is not None else None,
            headers=self._request.headers,
            auth=(
                BasicAuth(username=self._request.auth["username"], password=self._request.auth.get("password", ""))
                if self._request.auth is not None
                else USE_CLIENT_DEFAULT
            ),
            timeout=self._request.timeout or USE_CLIENT_DEFAULT,
            follow_redirects=self._request.allow_redirects,
        )
        return Response(
            url=str(response.url),
            method=response.request.method,
            status=response.status_code,
            headers=response.headers,
            cookies=to_simple_cookie(response.cookies),
            read=response.aread,
        )


class HttpxSession(BaseSession):
    """HTTP session implementation that wraps an :class:`httpx.AsyncClient`."""

    def __init__(
        self,
        timeout: float | None,
        verify: SSLContext | bool,
        proxy: str | dict[str, str | None] | None,
    ):
        """Instantiate an ``AsyncClient`` honoring timeout/SSL/proxy configuration."""
        if isinstance(proxy, dict):
            mounts = {scheme: AsyncHTTPTransport(proxy=proxy) for scheme, proxy in proxy.items() if proxy} or None
            proxy = None
        else:
            mounts = None

        self._client = AsyncClient(timeout=timeout, verify=verify, proxy=proxy, mounts=mounts)

    def make_request(self, request: Request) -> HttpxRequestContextManager:
        """Create a request context manager coupled with the shared client."""
        return HttpxRequestContextManager(request, self._client)

    async def close(self):
        """Close the ``AsyncClient`` to free connectors and sockets."""
        await self._client.aclose()
