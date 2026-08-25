import socket
import ssl
from typing import Any, Callable

import httpx
import httpx2
import pytest
from aiohttp import web
from aiohttp.client_exceptions import (
    ClientConnectorCertificateError,
    ClientConnectorDNSError,
    ClientConnectorError,
    ClientPayloadError,
    ClientProxyConnectionError,
    ContentTypeError,
    InvalidUrlClientError,
    ServerTimeoutError,
    TooManyRedirects,
)
from aiohttp.client_reqrep import ConnectionKey, RequestInfo
from multidict import CIMultiDict, CIMultiDictProxy
from yarl import URL

from aioscraper.config import Config, HttpBackend, SessionConfig
from aioscraper.core.session._errors import Classifier, client_errors
from aioscraper.core.session._httpx import make_classifier
from aioscraper.core.session.aiohttp import classify as classify_aiohttp
from aioscraper.core.session.factory import get_sessionmaker
from aioscraper.exceptions import ClientException, ConnectionFailed, DNSError, ProxyError, TLSError, TransportTimeout
from aioscraper.exceptions import InvalidURL as AioscraperInvalidURL
from aioscraper.exceptions import TooManyRedirects as AioscraperTooManyRedirects
from aioscraper.types import Request, Response, ScheduleRequest
from tests.mocks import MockAIOScraper

# what each backend raises for the same failure, and what it must become
EXPECTED: dict[str, type[ClientException] | None] = {
    "timeout": TransportTimeout,
    "dns": DNSError,
    "tls": TLSError,
    "proxy": ProxyError,
    "connection": ConnectionFailed,
    "truncated_body": ConnectionFailed,
    "raw_ssl": TLSError,
    "too_many_redirects": AioscraperTooManyRedirects,
    "invalid_url": AioscraperInvalidURL,
    "untranslated": None,
}


def _named_tuple(cls: Any, **values: Any) -> Any:
    "Fill whichever fields this aiohttp declares: they differ between the versions we support."
    return cls(**{name: values.get(name) for name in cls._fields})


_URL = URL("https://api.test.com/x")
_KEY = _named_tuple(ConnectionKey, host="api.test.com", port=443, is_ssl=True, ssl=True)
_REQUEST_INFO = _named_tuple(
    RequestInfo,
    url=_URL,
    method="GET",
    headers=CIMultiDictProxy(CIMultiDict()),
    real_url=_URL,
)


def _aiohttp_failure(category: str) -> BaseException:
    return {
        "timeout": lambda: ServerTimeoutError("timed out"),
        "dns": lambda: ClientConnectorDNSError(_KEY, OSError("name or service not known")),
        "tls": lambda: ClientConnectorCertificateError(_KEY, ssl.SSLCertVerificationError("bad certificate")),
        "proxy": lambda: ClientProxyConnectionError(_KEY, OSError("proxy refused")),
        "connection": lambda: ClientConnectorError(_KEY, OSError("connection refused")),
        "truncated_body": ClientPayloadError,
        "raw_ssl": lambda: ssl.SSLError("handshake failed"),
        "too_many_redirects": lambda: TooManyRedirects(_REQUEST_INFO, ()),
        "invalid_url": lambda: InvalidUrlClientError("::not a url"),
        "untranslated": lambda: ContentTypeError(_REQUEST_INFO, ()),
    }[category]()


def _caused_by(exc: BaseException, cause: BaseException) -> BaseException:
    exc.__cause__ = cause
    return exc


def _httpx_failure(module: Any, category: str) -> BaseException:
    return {
        "timeout": lambda: module.ReadTimeout("timed out"),
        "dns": lambda: _caused_by(module.ConnectError("name resolution failed"), socket.gaierror(-2, "no name")),
        "tls": lambda: _caused_by(
            module.ConnectError("certificate verify failed"),
            ssl.SSLCertVerificationError("bad certificate"),
        ),
        "proxy": lambda: module.ProxyError("proxy refused"),
        "connection": lambda: _caused_by(module.ConnectError("connection refused"), ConnectionRefusedError()),
        "truncated_body": lambda: module.RemoteProtocolError("peer closed connection"),
        "raw_ssl": lambda: ssl.SSLError("handshake failed"),
        "too_many_redirects": lambda: module.TooManyRedirects("too many redirects"),
        "invalid_url": lambda: module.UnsupportedProtocol("unsupported scheme"),
        "untranslated": lambda: module.DecodingError("broken gzip"),
    }[category]()


BACKENDS: dict[str, tuple[Classifier, Callable[[str], BaseException]]] = {
    "aiohttp": (classify_aiohttp, _aiohttp_failure),
    "httpx": (make_classifier(httpx), lambda category: _httpx_failure(httpx, category)),
    "httpx2": (make_classifier(httpx2), lambda category: _httpx_failure(httpx2, category)),
}


@pytest.mark.parametrize("backend", list(BACKENDS))
@pytest.mark.parametrize("category", list(EXPECTED))
def test_every_backend_classifies_a_failure_the_same_way(backend: str, category: str):
    classify, failure = BACKENDS[backend]

    assert classify(failure(category)) is EXPECTED[category]


def test_a_timeout_is_also_the_builtin_timeout_error():
    """aiohttp raises one on its own, so a policy or errback written against it keeps working."""
    assert issubclass(TransportTimeout, TimeoutError)


def test_a_failure_that_is_not_a_transport_one_is_left_alone():
    boom = ValueError("not a transport failure")

    with (
        pytest.raises(ValueError, match="not a transport failure") as excinfo,
        client_errors(lambda _: None, "https://api.test.com/x", "GET"),
    ):
        raise boom

    assert excinfo.value is boom


@pytest.fixture
def dead_url() -> str:
    "A port nothing listens on: bound to learn its number, then released."
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    return f"http://127.0.0.1:{port}/"


@pytest.mark.parametrize("backend", list(HttpBackend))
async def test_a_refused_connection_is_a_connection_failure(backend: HttpBackend, dead_url: str):
    session = get_sessionmaker(SessionConfig(http_backend=backend, timeout=5.0))()

    try:
        with pytest.raises(ConnectionFailed) as excinfo:
            async with session.make_request(Request(url=dead_url)):
                pass
    finally:
        await session.close()

    # the client's own exception is kept, so nothing is lost by translating it
    assert type(excinfo.value) is ConnectionFailed
    assert excinfo.value.__cause__ is not None
    assert excinfo.value.url == dead_url


class _StreamScraper:
    def __init__(self, url: str):
        self._url = url
        self.error: Exception | None = None

    async def __call__(self, schedule_request: ScheduleRequest):
        await schedule_request(Request(url=self._url, callback=self.parse, errback=self.on_error))

    async def parse(self, response: Response):
        await response.read()

    async def on_error(self, exc: Exception):
        self.error = exc


async def test_a_body_that_stops_early_is_a_connection_failure(mock_aioscraper: MockAIOScraper):
    """The failure lands in the body iterator rather than in the send, and must translate too."""

    async def truncated(request: web.BaseRequest) -> web.StreamResponse:
        response = web.StreamResponse(status=200, headers={"Content-Length": "4096"})
        await response.prepare(request)
        await response.write(b"x" * 16)
        # the announced body never arrives, and the connection goes away with it
        request.transport.close()  # type: ignore[reportOptionalMemberAccess]
        return response

    mock_aioscraper.server.add("https://api.test.com/truncated", handler=truncated)
    scraper = _StreamScraper("https://api.test.com/truncated")
    mock_aioscraper(scraper)
    # the default cap must not be what fails the read
    mock_aioscraper.config = Config(session=SessionConfig(max_response_body_size=None))

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    assert isinstance(scraper.error, ConnectionFailed)
