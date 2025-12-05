from ssl import SSLContext
from httpx import AsyncClient, BasicAuth

from .base import BaseSession
from ..types import Response, Request
from .._helpers.http import parse_cookies, to_simple_cookie


class HttpxSession(BaseSession):
    "Implementation of HTTP session using httpx."

    def __init__(self, timeout: float | None, verify: SSLContext | bool) -> None:
        self._client = AsyncClient(timeout=timeout, verify=verify)

    async def make_request(self, request: Request) -> Response:
        "Perform an HTTP request via httpx and wrap the result in `Response`."

        response = await self._client.request(
            url=request.url,
            method=request.method,
            params=request.params,
            data=request.data,
            json=request.json_data,
            cookies=parse_cookies(request.cookies) if request.cookies is not None else None,
            headers=request.headers,
            auth=(
                BasicAuth(username=request.auth["username"], password=request.auth.get("password", ""))
                if request.auth is not None
                else None
            ),
            timeout=request.timeout,
            follow_redirects=request.allow_redirects,
        )

        return Response(
            url=str(response.url),
            method=request.method,
            status=response.status_code,
            headers=response.headers,
            cookies=to_simple_cookie(response.cookies),
            content=response.read(),
        )

    async def close(self) -> None:
        await self._client.aclose()
