from aiohttp import ClientSession, ClientTimeout, TCPConnector
from aiohttp.helpers import BasicAuth

from .base import BaseSession
from ..types import Response, Request


class AiohttpSession(BaseSession):
    "Implementation of HTTP session using aiohttp."

    def __init__(self, timeout: float | None = None, ssl: bool | None = None) -> None:
        super().__init__(timeout, ssl)
        self._session = ClientSession(
            timeout=ClientTimeout(total=timeout),
            connector=TCPConnector(ssl=ssl) if ssl is not None else None,
        )

    async def make_request(self, request: Request) -> Response:
        "Perform an HTTP request via aiohttp and wrap the result in `Response`."
        async with self._session.request(
            url=request.url,
            method=request.method,
            params=request.params,
            data=request.data,
            json=request.json_data,
            cookies=request.cookies,
            headers=request.headers,
            proxy=request.proxy,
            proxy_auth=(
                BasicAuth(
                    login=request.proxy_auth["username"],
                    password=request.proxy_auth.get("password", ""),
                    encoding=request.proxy_auth.get("encoding", "latin1"),
                )
                if request.proxy_auth is not None
                else None
            ),
            proxy_headers=request.proxy_headers,
            auth=(
                BasicAuth(
                    login=request.auth["username"],
                    password=request.auth.get("password", ""),
                    encoding=request.auth.get("encoding", "latin1"),
                )
                if request.auth is not None
                else None
            ),
            timeout=ClientTimeout(total=request.timeout) if request.timeout is not None else None,
            allow_redirects=request.allow_redirects,
        ) as response:
            return Response(
                url=str(response.url),
                method=request.method,
                status=response.status,
                headers=response.headers,
                cookies=response.cookies,
                content=await response.read(),
            )

    async def close(self) -> None:
        await self._session.close()
