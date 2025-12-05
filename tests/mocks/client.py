from contextlib import contextmanager
from typing import Iterator, Sequence

from aiohttp import ClientRequest, TCPConnector
from aiohttp.tracing import Trace
from aiohttp.abc import ResolveResult
from httpx import AsyncClient, URL, Headers


@contextmanager
def patch_aiohttp(port_: int) -> Iterator[None]:
    old_resolver_mock = TCPConnector._resolve_host

    async def _resolve_host(self, host: str, port: int, traces: Sequence[Trace] | None = None) -> list[ResolveResult]:
        return [
            {
                "hostname": host,
                "host": "127.0.0.1",
                "port": port_,
                "family": self._family,
                "proto": 0,
                "flags": 0,
            }
        ]

    TCPConnector._resolve_host = _resolve_host

    old_is_ssl = ClientRequest.is_ssl

    ClientRequest.is_ssl = lambda self: False

    try:
        yield
    finally:
        TCPConnector._resolve_host = old_resolver_mock
        ClientRequest.is_ssl = old_is_ssl


@contextmanager
def patch_httpx(port_: int) -> Iterator[None]:
    old_request = AsyncClient.request

    async def _request(self, method, url, *args, **kwargs):
        original_url = URL(url)
        host = original_url.host or ""
        host_port = f"{host}:{original_url.port}" if original_url.port else host

        headers = Headers(kwargs.pop("headers", None) or {})
        if host_port:
            headers["Host"] = host_port

        kwargs["headers"] = headers

        proxied_url = original_url.copy_with(scheme="http", host="127.0.0.1", port=port_)
        return await old_request(self, method, proxied_url, *args, **kwargs)

    AsyncClient.request = _request
    try:
        yield
    finally:
        AsyncClient.request = old_request
