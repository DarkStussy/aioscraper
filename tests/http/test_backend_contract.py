from contextlib import asynccontextmanager
from http.cookies import SimpleCookie
from typing import Any, AsyncGenerator

import pytest
from aiohttp import ClientTimeout
from aiohttp.helpers import BasicAuth
from httpx import AsyncClient

from aioscraper.core.session.aiohttp import AiohttpSession
from aioscraper.core.session.httpx import HttpxSession
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


@pytest.fixture
def httpx_session() -> HttpxSession:
    return HttpxSession(timeout=1.0, verify=True, proxy=None)


@pytest.mark.parametrize(("kwargs", "option"), UNSUPPORTED_BY_HTTPX)
async def test_httpx_rejects_unsupported_options(httpx_session: HttpxSession, kwargs: dict, option: str):
    """Options httpx cannot honor must fail loudly instead of being dropped."""
    request = Request(url="https://api.test.com/resource", **kwargs)

    with pytest.raises(UnsupportedRequestOption) as excinfo:
        httpx_session.make_request(request)

    assert excinfo.value.option == option
    assert excinfo.value.backend == "httpx"
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


async def test_httpx_allows_max_redirects_when_redirects_are_disabled(httpx_session: HttpxSession):
    """max_redirects is meaningless with allow_redirects=False, so it must not raise."""
    request = Request(url="https://api.test.com/resource", allow_redirects=False, max_redirects=3)

    assert httpx_session.make_request(request) is not None

    await httpx_session.close()


async def test_httpx_allows_the_default_max_redirects(httpx_session: HttpxSession):
    request = Request(url="https://api.test.com/resource", max_redirects=DEFAULT_MAX_REDIRECTS)

    assert httpx_session.make_request(request) is not None

    await httpx_session.close()


async def test_httpx_allows_auth_without_an_encoding(httpx_session: HttpxSession):
    """Only the encoding field is unsupported; credentials themselves are sent."""
    request = Request(url="https://api.test.com/resource", auth={"username": "user", "password": "pass"})

    assert httpx_session.make_request(request) is not None


async def test_httpx_reports_the_redirect_limit_of_the_client():
    """A provided client keeps its own limit, so the message must not name the built-in default."""
    async with AsyncClient(max_redirects=3) as client:
        session = HttpxSession(client=client)

        with pytest.raises(UnsupportedRequestOption, match="is 3 here"):
            session.make_request(Request(url="https://api.test.com/resource", max_redirects=5))


@pytest.mark.parametrize("encoding", ["utf-8", "UTF8", "u8"])
async def test_httpx_accepts_an_encoding_that_means_utf_8(httpx_session: HttpxSession, encoding: str):
    """UTF-8 is what httpx sends, however it is spelled."""
    request = Request(url="https://api.test.com/resource", auth={"username": "user", "encoding": encoding})

    assert httpx_session.make_request(request) is not None

    await httpx_session.close()
