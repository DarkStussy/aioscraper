from ssl import SSLContext
from httpx import AsyncClient, BasicAuth, USE_CLIENT_DEFAULT, AsyncHTTPTransport

from .base import BaseSession
from ..types import Response, Request
from .._helpers.http import parse_cookies, parse_url, to_simple_cookie


class HttpxSession(BaseSession):
    "Implementation of HTTP session using httpx."

    def __init__(
        self,
        timeout: float | None,
        verify: SSLContext | bool,
        proxy: str | dict[str, str | None] | None,
    ):
        if isinstance(proxy, dict):
            mounts = {scheme: AsyncHTTPTransport(proxy=proxy) for scheme, proxy in proxy.items() if proxy} or None
            proxy = None
        else:
            mounts = None

        self._client = AsyncClient(timeout=timeout, verify=verify, proxy=proxy, mounts=mounts)

    async def make_request(self, request: Request) -> Response:
        "Perform an HTTP request via httpx and wrap the result in `Response`."

        if isinstance(request.data, dict):
            content, data = None, request.data
        else:
            content, data = request.data, None

        response = await self._client.request(
            url=str(parse_url(request.url, request.params)),
            method=request.method,
            content=content,
            data=data,
            files=request.files,
            json=request.json_data,
            cookies=parse_cookies(request.cookies) if request.cookies is not None else None,
            headers=request.headers,
            auth=(
                BasicAuth(username=request.auth["username"], password=request.auth.get("password", ""))
                if request.auth is not None
                else USE_CLIENT_DEFAULT
            ),
            timeout=request.timeout or USE_CLIENT_DEFAULT,
            follow_redirects=request.allow_redirects,
        )

        return Response(
            url=str(response.url),
            method=request.method,
            status=response.status_code,
            headers=response.headers,
            cookies=to_simple_cookie(response.cookies),
            content=await response.aread(),
        )

    async def close(self):
        await self._client.aclose()
