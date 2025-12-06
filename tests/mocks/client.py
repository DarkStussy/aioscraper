from contextlib import contextmanager
from typing import Iterator, Sequence

from aiohttp import ClientRequest, TCPConnector
from aiohttp.tracing import Trace
from aiohttp.abc import ResolveResult
from httpx import AsyncClient, URL


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
    old_build_request = AsyncClient.build_request
    old_send = AsyncClient.send
    old_build_redirect = AsyncClient._build_redirect_request

    def _build_request(self, method, url, *args, **kwargs):
        original_url = URL(url)
        host = original_url.host or ""
        host_port = f"{host}:{original_url.port}" if original_url.port else host

        proxied = original_url.copy_with(scheme="http", host="127.0.0.1", port=port_)
        request = old_build_request(self, method, proxied, *args, **kwargs)

        if host_port:
            request.headers["Host"] = host_port

        request.extensions["original_url"] = original_url
        return request

    async def _send(self, request, *args, **kwargs):
        original_url = request.extensions.get("original_url", request.url)

        host = original_url.host or ""
        host_port = f"{host}:{original_url.port}" if original_url.port else host
        request.url = original_url.copy_with(scheme="http", host="127.0.0.1", port=port_)
        if host_port:
            request.headers["Host"] = host_port

        response = await old_send(self, request, *args, **kwargs)

        if response.request is not None and "original_url" in response.request.extensions:
            response.request.url = response.request.extensions["original_url"]

        for hist in response.history:
            if hist.request is not None and "original_url" in hist.request.extensions:
                hist.request.url = hist.request.extensions["original_url"]

        if response.url.host == "127.0.0.1" and "original_url" in request.extensions:
            response.request.url = request.extensions["original_url"]

        return response

    def _build_redirect_request(self, request, response):
        next_request = old_build_redirect(self, request, response)

        base_original = request.extensions.get("original_url", request.url)
        location = response.headers.get("Location")
        try:
            target_original = URL(location) if location is not None else next_request.url
        except Exception:
            target_original = next_request.url

        if not target_original.is_absolute_url:
            target_original = base_original.join(target_original)

        host = target_original.host or ""
        host_port = f"{host}:{target_original.port}" if target_original.port else host

        next_request.url = target_original.copy_with(scheme="http", host="127.0.0.1", port=port_)
        if host_port:
            next_request.headers["Host"] = host_port
        next_request.extensions["original_url"] = target_original

        return next_request

    AsyncClient.build_request = _build_request
    AsyncClient.send = _send
    AsyncClient._build_redirect_request = _build_redirect_request
    try:
        yield
    finally:
        AsyncClient.build_request = old_build_request
        AsyncClient.send = old_send
        AsyncClient._build_redirect_request = old_build_redirect
