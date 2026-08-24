from contextlib import asynccontextmanager
from http.cookies import SimpleCookie
from typing import Any, AsyncGenerator, Callable, NamedTuple

import httpx
import httpx2
import pytest
from aiohttp import ClientTimeout
from aiohttp.helpers import BasicAuth

from aioscraper.core.session._httpx import BaseHttpxSession
from aioscraper.core.session.aiohttp import AiohttpSession
from aioscraper.core.session.httpx import HttpxSession
from aioscraper.core.session.httpx2 import Httpx2Session
from aioscraper.exceptions import UnsupportedRequestOption
from aioscraper.types import Request
from aioscraper.types.session import DEFAULT_MAX_REDIRECTS

UNSUPPORTED_BY_HTTPX = (
    pytest.param({"proxy": "http://proxy:8080"}, "proxy", id="proxy"),
    pytest.param({"proxy_auth": {"username": "user", "password": "pass"}}, "proxy_auth", id="proxy_auth"),
    pytest.param({"proxy_headers": {"X-Proxy": "1"}}, "proxy_headers", id="proxy_headers"),
    pytest.param({"max_redirects": 3}, "max_redirects", id="max_redirects"),
    pytest.param(
        {"auth": {"username": "user", "password": "pass", "encoding": "latin1"}},
        "auth.encoding",
        id="auth-encoding",
    ),
)


class HttpxBackend(NamedTuple):
    """One httpx-compatible backend, so every contract below is checked on both."""

    name: str
    session_cls: type[BaseHttpxSession]
    client_cls: Callable[..., Any]


HTTPX_BACKENDS = (
    HttpxBackend("httpx", HttpxSession, httpx.AsyncClient),
    HttpxBackend("httpx2", Httpx2Session, httpx2.AsyncClient),
)


@pytest.fixture(params=HTTPX_BACKENDS, ids=[backend.name for backend in HTTPX_BACKENDS])
def httpx_backend(request: pytest.FixtureRequest) -> HttpxBackend:
    return request.param


@pytest.fixture
def httpx_session(httpx_backend: HttpxBackend) -> BaseHttpxSession:
    return httpx_backend.session_cls(timeout=1.0, verify=True, proxy=None)


@pytest.mark.parametrize(("kwargs", "option"), UNSUPPORTED_BY_HTTPX)
async def test_httpx_rejects_unsupported_options(
    httpx_session: BaseHttpxSession,
    httpx_backend: HttpxBackend,
    kwargs: dict,
    option: str,
):
    """Options httpx cannot honor must fail loudly instead of being dropped."""
    request = Request(url="https://api.test.com/resource", **kwargs)

    with pytest.raises(UnsupportedRequestOption) as excinfo:
        httpx_session.make_request(request)

    assert excinfo.value.option == option
    assert excinfo.value.backend == httpx_backend.name
    # The message must say what to do instead, not only what failed.
    assert excinfo.value.hint

    await httpx_session.close()


class _StubContent:
    async def iter_chunked(self, n: int) -> AsyncGenerator[bytes, None]:
        yield b""


class _StubResponse:
    url = "https://api.test.com/resource"
    method = "GET"
    status = 200
    headers: dict[str, str] = {}  # noqa: RUF012
    cookies = SimpleCookie()
    content = _StubContent()


@asynccontextmanager
async def _stub_request(**kwargs: Any) -> AsyncGenerator[_StubResponse, None]:
    yield _StubResponse()


# aiohttp>=3.14 deprecates BasicAuth, which the backend still builds for auth/proxy_auth.
# Scoped here so the warning still fails the suite anywhere else.
@pytest.mark.filterwarnings("ignore:BasicAuth is deprecated:DeprecationWarning")
@pytest.mark.parametrize(("kwargs", "option"), UNSUPPORTED_BY_HTTPX)
async def test_aiohttp_forwards_the_same_options(kwargs: dict, option: str):
    """The aiohttp backend must pass each option through to ClientSession.request()."""
    captured: dict[str, Any] = {}
    session = AiohttpSession(timeout=ClientTimeout(total=1.0), connector=None, proxy=None)

    def spy(**request_kwargs: Any):
        captured.update(request_kwargs)
        return _stub_request(**request_kwargs)

    session._session.request = spy  # type: ignore[reportAttributeAccessIssue]

    async with session.make_request(Request(url="https://api.test.com/resource", **kwargs)) as response:
        assert response.status == 200

    # the option of the httpx failure is not always the request field it comes from
    field, value = next(iter(kwargs.items()))
    if field in ("auth", "proxy_auth"):
        # Converted to aiohttp's BasicAuth rather than forwarded verbatim, encoding included.
        assert captured[field] == BasicAuth(
            login=value["username"],
            password=value["password"],
            encoding=value.get("encoding", "latin1"),
        )
    else:
        assert captured[field] == value

    await session.close()


async def test_httpx_allows_max_redirects_when_redirects_are_disabled(httpx_session: BaseHttpxSession):
    """max_redirects is meaningless with allow_redirects=False, so it must not raise."""
    request = Request(url="https://api.test.com/resource", allow_redirects=False, max_redirects=3)

    assert httpx_session.make_request(request) is not None

    await httpx_session.close()


async def test_httpx_allows_the_default_max_redirects(httpx_session: BaseHttpxSession):
    request = Request(url="https://api.test.com/resource", max_redirects=DEFAULT_MAX_REDIRECTS)

    assert httpx_session.make_request(request) is not None

    await httpx_session.close()


async def test_httpx_allows_auth_without_an_encoding(httpx_session: BaseHttpxSession):
    """Only the encoding field is unsupported; credentials themselves are sent."""
    request = Request(url="https://api.test.com/resource", auth={"username": "user", "password": "pass"})

    assert httpx_session.make_request(request) is not None


async def test_httpx_reports_the_redirect_limit_of_the_client(httpx_backend: HttpxBackend):
    """A provided client keeps its own limit, so the message must not name the built-in default."""
    async with httpx_backend.client_cls(max_redirects=3) as client:
        session = httpx_backend.session_cls(client=client)

        with pytest.raises(UnsupportedRequestOption, match="is 3 here"):
            session.make_request(Request(url="https://api.test.com/resource", max_redirects=5))


class _StubHttpxResponse:
    """Enough of an httpx response for the session to wrap, so no connection is needed."""

    status_code = 200
    headers = httpx.Headers()
    cookies: dict[str, str] = {}  # noqa: RUF012

    def __init__(self, request: Any):
        self.request = request
        self.url = request.url

    async def aiter_bytes(self, chunk_size: int | None = None) -> AsyncGenerator[bytes, None]:
        yield b""

    async def aclose(self): ...


# 0 included: the dispatcher rejects it, but the session must send what it was given rather than
# read it as "no timeout" and fall back to the client
@pytest.mark.parametrize("timeout", [0.25, 0, None])
async def test_httpx_sends_the_request_timeout(httpx_backend: HttpxBackend, timeout: float | None):
    session = httpx_backend.session_cls(timeout=5.0)
    captured: dict[str, Any] = {}

    async def spy(request: Any, **kwargs: Any) -> _StubHttpxResponse:
        captured.update(request.extensions["timeout"])
        return _StubHttpxResponse(request)

    session._client.send = spy  # type: ignore[reportAttributeAccessIssue]

    async with session.make_request(Request(url="https://api.test.com/resource", timeout=timeout)) as response:
        assert response.status == 200

    expected = 5.0 if timeout is None else timeout
    assert captured == {"connect": expected, "read": expected, "write": expected, "pool": expected}

    await session.close()


@pytest.mark.parametrize("timeout", [0.25, 0, None])
async def test_aiohttp_sends_the_request_timeout(timeout: float | None):
    """The same values, so a request behaves the same whichever backend sends it."""
    captured: dict[str, Any] = {}
    session = AiohttpSession(timeout=ClientTimeout(total=5.0), connector=None, proxy=None)

    def spy(**request_kwargs: Any):
        captured.update(request_kwargs)
        return _stub_request(**request_kwargs)

    session._session.request = spy  # type: ignore[reportAttributeAccessIssue]

    async with session.make_request(Request(url="https://api.test.com/resource", timeout=timeout)) as response:
        assert response.status == 200

    assert captured["timeout"] == (session._session.timeout if timeout is None else ClientTimeout(total=timeout))

    await session.close()


@pytest.mark.parametrize("encoding", ["utf-8", "UTF8", "u8"])
async def test_httpx_accepts_an_encoding_that_means_utf_8(httpx_session: BaseHttpxSession, encoding: str):
    """UTF-8 is what httpx sends, however it is spelled."""
    request = Request(url="https://api.test.com/resource", auth={"username": "user", "encoding": encoding})

    assert httpx_session.make_request(request) is not None

    await httpx_session.close()
