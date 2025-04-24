from aiohttp import ClientSession, ClientTimeout, TCPConnector
from aiohttp.helpers import BasicAuth

from .base import BaseSession
from ..types import Response, Request


class AiohttpSession(BaseSession):
    "Implementation of HTTP session using aiohttp"

    def __init__(self, timeout: float | None = None, ssl: bool | None = None, **kwargs) -> None:
        super().__init__(timeout, ssl)
        self._session = ClientSession(
            timeout=ClientTimeout(total=timeout),
            connector=TCPConnector(ssl=ssl) if ssl is not None else None,
            **kwargs,
        )

    async def make_request(self, request: Request) -> Response:
        async with self._session.request(
            url=request.url,
            method=request.method,
            params=request.params,
            data=request.data,
            json=request.json_data,
            cookies=request.cookies,
            headers=request.headers,
            proxy=request.proxy,
            auth=(
                BasicAuth(login=request.auth["username"], password=request.auth["password"])
                if request.auth is not None
                else None
            ),
            timeout=ClientTimeout(total=request.timeout) if request.timeout is not None else None,
        ) as response:
            return Response(
                url=request.url,
                method=request.method,
                params=request.params,
                status=response.status,
                headers=dict(response.headers),
                cookies={k: f"{v.key}={v.value}" for k, v in response.cookies.items()},
                content=await response.read(),
                content_type=response.headers.get("Content-Type"),
            )

    async def close(self) -> None:
        await self._session.close()
