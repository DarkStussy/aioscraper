import pytest

from aioscraper.core.session._httpx import BaseHttpxSession
from aioscraper.core.session.httpx import HttpxSession
from aioscraper.core.session.httpx2 import Httpx2Session
from aioscraper.types.session import DEFAULT_MAX_REDIRECTS


@pytest.fixture(params=[HttpxSession, Httpx2Session], ids=["httpx", "httpx2"])
def session_cls(request: pytest.FixtureRequest) -> type[BaseHttpxSession]:
    return request.param


def test_httpx_session_uses_proxy_string(monkeypatch, session_cls: type[BaseHttpxSession]):
    captured: dict[str, object] = {}

    class DummyClient:
        def __init__(self, *, timeout, verify, proxy=None, mounts=None, max_redirects=None):
            captured["timeout"] = timeout
            captured["verify"] = verify
            captured["proxy"] = proxy
            captured["mounts"] = mounts
            captured["max_redirects"] = max_redirects

    monkeypatch.setattr(session_cls, "_binding", session_cls._binding._replace(async_client=DummyClient))

    session_cls(timeout=5, verify=True, proxy="http://proxy:8080")

    assert captured["proxy"] == "http://proxy:8080"
    assert captured["mounts"] is None
    assert captured["timeout"] == 5
    assert captured["verify"] is True
    # Without this httpx would silently use its own default of 20.
    assert captured["max_redirects"] == DEFAULT_MAX_REDIRECTS


def test_httpx_session_builds_mounts_for_proxy_dict(monkeypatch, session_cls: type[BaseHttpxSession]):
    captured: dict[str, object] = {}
    transports: list[str] = []

    class DummyTransport:
        def __init__(self, *, proxy):
            transports.append(proxy)

    class DummyClient:
        def __init__(self, *, timeout, verify, proxy=None, mounts=None, max_redirects=None):
            captured["proxy"] = proxy
            captured["mounts"] = mounts

    monkeypatch.setattr(
        session_cls,
        "_binding",
        session_cls._binding._replace(async_client=DummyClient, async_http_transport=DummyTransport),
    )

    proxy_map: dict[str, str | None] = {"http://": "http://proxy:8080", "https://": "http://proxy:8443"}

    session_cls(timeout=None, verify=False, proxy=proxy_map)

    assert captured["proxy"] is None  # moved into mounts
    assert isinstance(captured["mounts"], dict)
    assert set(captured["mounts"].keys()) == set(proxy_map.keys())
    assert transports == list(proxy_map.values())
