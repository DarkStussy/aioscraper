from contextlib import AbstractContextManager, contextmanager
from typing import Any, Iterator, Sequence

import httpx
import httpx2
from aiohttp import ClientRequest, TCPConnector
from aiohttp.abc import ResolveResult
from aiohttp.tracing import Trace


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
            },
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
def _patch_httpx_module(module: Any, port_: int) -> Iterator[None]:
    "Route the client of httpx or of its httpx2 fork to the local server; their APIs are the same."
    client_cls, url_cls = module.AsyncClient, module.URL

    old_build_request = client_cls.build_request
    old_send = client_cls.send
    old_build_redirect = client_cls._build_redirect_request

    def _build_request(self, method, url, *args, **kwargs):
        original_url = url_cls(url)
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

        if response.request is not None and response.url.host == "127.0.0.1" and "original_url" in request.extensions:
            response.request.url = request.extensions["original_url"]

        return response

    def _build_redirect_request(self, request, response):
        next_request = old_build_redirect(self, request, response)

        base_original = request.extensions.get("original_url", request.url)
        location = response.headers.get("Location")
        try:
            target_original = url_cls(location) if location is not None else next_request.url
        except:  # noqa: E722
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

    client_cls.build_request = _build_request
    client_cls.send = _send
    client_cls._build_redirect_request = _build_redirect_request
    try:
        yield
    finally:
        client_cls.build_request = old_build_request
        client_cls.send = old_send
        client_cls._build_redirect_request = old_build_redirect


def patch_httpx(port_: int) -> AbstractContextManager[None]:
    return _patch_httpx_module(httpx, port_)


def patch_httpx2(port_: int) -> AbstractContextManager[None]:
    return _patch_httpx_module(httpx2, port_)
