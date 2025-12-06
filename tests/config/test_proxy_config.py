from aioscraper.session.httpx import HttpxSession


def test_httpx_session_uses_proxy_string(monkeypatch):
    captured: dict[str, object] = {}

    class DummyClient:
        def __init__(self, *, timeout, verify, proxy=None, mounts=None):
            captured["timeout"] = timeout
            captured["verify"] = verify
            captured["proxy"] = proxy
            captured["mounts"] = mounts

    monkeypatch.setattr("aioscraper.session.httpx.AsyncClient", DummyClient)

    HttpxSession(timeout=5, verify=True, proxy="http://proxy:8080")

    assert captured["proxy"] == "http://proxy:8080"
    assert captured["mounts"] is None
    assert captured["timeout"] == 5
    assert captured["verify"] is True


def test_httpx_session_builds_mounts_for_proxy_dict(monkeypatch):
    captured: dict[str, object] = {}
    transports: list[str] = []

    class DummyTransport:
        def __init__(self, *, proxy):
            transports.append(proxy)

    class DummyClient:
        def __init__(self, *, timeout, verify, proxy=None, mounts=None):
            captured["proxy"] = proxy
            captured["mounts"] = mounts

    monkeypatch.setattr("aioscraper.session.httpx.AsyncHTTPTransport", DummyTransport)
    monkeypatch.setattr("aioscraper.session.httpx.AsyncClient", DummyClient)

    proxy_map = {"http://": "http://proxy:8080", "https://": "http://proxy:8443"}

    HttpxSession(timeout=None, verify=False, proxy=proxy_map)

    assert captured["proxy"] is None  # moved into mounts
    assert isinstance(captured["mounts"], dict)
    assert set(captured["mounts"].keys()) == set(proxy_map.keys())
    assert transports == list(proxy_map.values())
