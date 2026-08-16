from aiohttp import ClientSession, ClientTimeout, FormData, TCPConnector
from aiohttp.helpers import BasicAuth

from aioscraper.types import Request, Response

from .base import BaseRequestContextManager, BaseSession, resolve_client_ownership


class AiohttpRequestContextManager(BaseRequestContextManager):
    """aiohttp-backed context manager that issues a single HTTP request."""

    def __init__(self, request: Request, session: ClientSession, max_body_size: int | None = None):
        super().__init__(request)
        self._session = session
        self._max_body_size = max_body_size

    async def __aenter__(self) -> Response:
        """Prepare payload/files, dispatch the request and wrap the aiohttp response."""
        data = self._request.data

        if self._request.files is not None:
            form = FormData()

            if isinstance(self._request.data, dict):
                for key, value in self._request.data.items():
                    form.add_field(key, value)

            for name, file in self._request.files.items():
                form.add_field(name, file.value, filename=file.name, content_type=file.content_type)

            data = form

        response = await self._exit_stack.enter_async_context(
            self._session.request(
                url=self._request.url,
                method=self._request.method,
                params=self._request.params,
                data=data,
                json=self._request.json_data,
                cookies=self._request.cookies,
                headers=self._request.headers,
                proxy=self._request.proxy,
                proxy_auth=(
                    BasicAuth(
                        login=self._request.proxy_auth["username"],
                        password=self._request.proxy_auth.get("password", ""),
                        encoding=self._request.proxy_auth.get("encoding", "latin1"),
                    )
                    if self._request.proxy_auth is not None
                    else None
                ),
                proxy_headers=self._request.proxy_headers,
                auth=(
                    BasicAuth(
                        login=self._request.auth["username"],
                        password=self._request.auth.get("password", ""),
                        encoding=self._request.auth.get("encoding", "latin1"),
                    )
                    if self._request.auth is not None
                    else None
                ),
                timeout=(
                    ClientTimeout(total=self._request.timeout)
                    if self._request.timeout is not None
                    else self._session.timeout
                ),
                allow_redirects=self._request.allow_redirects,
                max_redirects=self._request.max_redirects,
            ),
        )
        return Response(
            url=str(response.url),
            method=response.method,
            status=response.status,
            headers=response.headers,
            cookies=response.cookies,
            aiter_bytes=response.content.iter_chunked,
            max_body_size=self._max_body_size,
        )


class AiohttpSession(BaseSession):
    """HTTP session implementation that reuses a shared :class:`ClientSession`.

    Args:
        timeout (ClientTimeout | None): Client-wide timeout; ``None`` leaves the aiohttp default.
        connector (TCPConnector | None): Connector carrying the SSL settings and connection pool.
        proxy (str | None): Proxy applied to every request.
        max_body_size (int | None): Cap on a response body in bytes; ``None`` disables the cap.
        client (ClientSession | None): Send through this client instead of creating one. Its own
            configuration is used as it is, which makes ``timeout``, ``connector`` and ``proxy``
            inapplicable.
        owns_client (bool | None): Close ``client`` on :meth:`close`. Defaults to ``False`` for a
            provided client and ``True`` for one created here.

    Raises:
        ValueError: ``owns_client`` is ``False`` without a ``client``.
    """

    def __init__(
        self,
        *,
        timeout: ClientTimeout | None = None,
        connector: TCPConnector | None = None,
        proxy: str | None = None,
        max_body_size: int | None = None,
        client: ClientSession | None = None,
        owns_client: bool | None = None,
    ):
        super().__init__(owns_client=resolve_client_ownership(client, owns_client))
        self._max_body_size = max_body_size
        self._session = (
            client if client is not None else ClientSession(timeout=timeout, connector=connector, proxy=proxy)
        )

    def make_request(self, request: Request) -> AiohttpRequestContextManager:
        """Create an aiohttp request context manager bound to the shared client."""
        return AiohttpRequestContextManager(request, self._session, self._max_body_size)

    async def _close_client(self):
        """Close the underlying ``ClientSession`` and release network resources."""
        await self._session.close()
