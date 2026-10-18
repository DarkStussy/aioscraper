import asyncio
from contextlib import suppress
from typing import AsyncIterator

import pytest

from aioscraper.config import HttpBackend, SessionConfig
from aioscraper.core.session import get_sessionmaker
from aioscraper.core.session._httpx import BaseHttpxSession
from aioscraper.core.session.httpx import HttpxSession
from aioscraper.core.session.httpx2 import Httpx2Session
from aioscraper.exceptions import TransportError
from aioscraper.types.session import DEFAULT_MAX_REDIRECTS, Request


@pytest.fixture(params=[HttpxSession, Httpx2Session], ids=["httpx", "httpx2"])
def session_cls(request: pytest.FixtureRequest) -> type[BaseHttpxSession]:
    return request.param


def test_httpx_session_uses_proxy_string(monkeypatch, session_cls: type[BaseHttpxSession]):
    captured: dict[str, object] = {}

    class DummyClient:
        def __init__(self, *, timeout, verify, proxy=None, mounts=None, max_redirects=None, trust_env=True):
            captured["timeout"] = timeout
            captured["verify"] = verify
            captured["proxy"] = proxy
            captured["mounts"] = mounts
            captured["max_redirects"] = max_redirects
            captured["trust_env"] = trust_env

    monkeypatch.setattr(session_cls, "_binding", session_cls._binding._replace(async_client=DummyClient))

    session_cls(timeout=5, verify=True, proxy="http://proxy:8080")

    assert captured["proxy"] == "http://proxy:8080"
    assert captured["mounts"] is None
    assert captured["timeout"] == 5
    assert captured["verify"] is True
    # Without this httpx would silently use its own default of 20.
    assert captured["max_redirects"] == DEFAULT_MAX_REDIRECTS
    # httpx defaults to True, aiohttp to False
    assert captured["trust_env"] is False


def test_httpx_session_builds_mounts_for_proxy_dict(monkeypatch, session_cls: type[BaseHttpxSession]):
    captured: dict[str, object] = {}
    transports: list[dict[str, object]] = []

    class DummyTransport:
        def __init__(self, *, proxy, verify, trust_env):
            transports.append({"proxy": proxy, "verify": verify, "trust_env": trust_env})

    class DummyClient:
        def __init__(self, *, timeout, verify, proxy=None, mounts=None, max_redirects=None, trust_env=True):
            captured["proxy"] = proxy
            captured["mounts"] = mounts

    monkeypatch.setattr(
        session_cls,
        "_binding",
        session_cls._binding._replace(async_client=DummyClient, async_http_transport=DummyTransport),
    )

    proxy_map: dict[str, str | None] = {"http://": "http://proxy:8080", "https://": "http://proxy:8443"}

    session_cls(timeout=None, verify=False, proxy=proxy_map, trust_env=True)

    assert captured["proxy"] is None  # moved into mounts
    assert isinstance(captured["mounts"], dict)
    assert set(captured["mounts"].keys()) == set(proxy_map.keys())
    assert transports == [{"proxy": url, "verify": False, "trust_env": True} for url in proxy_map.values()]


BACKENDS = [HttpBackend.AIOHTTP, HttpBackend.HTTPX, HttpBackend.HTTPX2]
PROXY_VARIABLES = ("http_proxy", "https_proxy", "all_proxy", "no_proxy")


@pytest.fixture
async def env_proxy(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[list[str]]:
    "A proxy named by http_proxy; collects the request lines it receives."
    request_lines: list[str] = []

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        request_lines.append((await reader.readline()).decode())
        while await reader.readline() not in (b"\r\n", b""):
            pass

        writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    for name in PROXY_VARIABLES:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.upper(), raising=False)

    monkeypatch.setenv("http_proxy", f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}")
    async with server:
        yield request_lines


@pytest.mark.parametrize("backend", BACKENDS)
@pytest.mark.parametrize("trust_env", [True, False])
async def test_trust_env_routes_through_the_environment_proxy(
    env_proxy: list[str],
    backend: HttpBackend,
    trust_env: bool,
):
    session = get_sessionmaker(SessionConfig(http_backend=backend, trust_env=trust_env, timeout=5.0))()
    try:
        # sent directly, the reserved .test domain does not resolve
        with suppress(TransportError):
            async with session.make_request(Request("http://scraper.test/page")) as response:
                await response.read()
    finally:
        await session.close()

    assert env_proxy == (["GET http://scraper.test/page HTTP/1.1\r\n"] if trust_env else [])


@pytest.mark.parametrize("backend", BACKENDS)
async def test_an_unsupported_environment_proxy_is_ignored_by_default(monkeypatch, backend: HttpBackend):
    # without socksio, an httpx client that reads it fails to build
    monkeypatch.setenv("ALL_PROXY", "socks5h://localhost:1080")

    await get_sessionmaker(SessionConfig(http_backend=backend))().close()
