import codecs
import socket
from ssl import SSLContext
from types import ModuleType
from typing import TYPE_CHECKING, Any, Callable, ClassVar, NamedTuple, cast

from multidict import CIMultiDict, CIMultiDictProxy

from aioscraper import exceptions
from aioscraper._helpers.http import parse_cookies, parse_url, to_simple_cookie
from aioscraper.exceptions import (
    ClientException,
    ConnectionFailed,
    DNSError,
    ProxyError,
    TransportTimeout,
    UnsupportedRequestOption,
)
from aioscraper.types import Request, Response
from aioscraper.types.session import DEFAULT_MAX_REDIRECTS

from ._errors import (
    Classifier,
    caused_by,
    classify_tls,
    client_errors,
    deadline_for,
    guard_stream,
    within_deadline,
)
from .base import BaseRequestContextManager, BaseSession, resolve_client_ownership
from .factory import HttpxClient

if TYPE_CHECKING:
    from httpx import AsyncClient

# httpx resolves proxies per transport and redirect limits per client, so none of these
# can vary per request without building a client for every request.
_UNSUPPORTED_HINTS = {
    "proxy": "Set SessionConfig.proxy, or use the aiohttp backend.",
    "proxy_auth": "Embed the credentials in the SessionConfig.proxy URL, or use the aiohttp backend.",
    "proxy_headers": "Use the aiohttp backend.",
}


class HttpxBinding(NamedTuple):
    """The classes and sentinels of one httpx-compatible package.

    httpx2 is a fork of httpx 0.28.1 and supports the APIs used below, so a single implementation
    serves both, but their classes and sentinels are distinct objects that cannot be mixed. The
    members are typed as plain callables because of that: naming the classes of one package would
    reject those of the other.

    Attributes:
        backend (str): Backend name reported by :class:`UnsupportedRequestOption`.
        async_client (Callable[..., Any]): ``AsyncClient`` of the package.
        async_http_transport (Callable[..., Any]): ``AsyncHTTPTransport``, mounted per scheme for
            a proxy mapping.
        basic_auth (Callable[..., Any]): ``BasicAuth``, built for a request that carries
            credentials.
        use_client_default (Any): ``USE_CLIENT_DEFAULT`` sentinel, sent when it does not.
        classify (Classifier): Maps a failure of the package onto the neutral classes.
    """

    backend: str
    async_client: Callable[..., Any]
    async_http_transport: Callable[..., Any]
    basic_auth: Callable[..., Any]
    use_client_default: Any
    classify: Classifier


def make_classifier(module: ModuleType) -> Classifier:
    "Classifier for one httpx-compatible package; their exception classes are unrelated."
    timeout_exception = module.TimeoutException
    proxy_error = module.ProxyError
    network_error = module.NetworkError
    remote_protocol_error = module.RemoteProtocolError
    too_many_redirects = module.TooManyRedirects
    invalid_url = (module.InvalidURL, module.UnsupportedProtocol)

    def classify(exc: BaseException) -> type[ClientException] | None:
        if isinstance(exc, timeout_exception):
            return TransportTimeout

        if isinstance(exc, proxy_error):
            return ProxyError

        # httpx reports every connect failure as ConnectError, so what it wrapped tells them apart
        if tls_error := classify_tls(exc):
            return tls_error

        if isinstance(exc, network_error):
            return DNSError if caused_by(exc, socket.gaierror) else ConnectionFailed

        # the server closed the connection before the response was complete
        if isinstance(exc, remote_protocol_error):
            return ConnectionFailed

        if isinstance(exc, too_many_redirects):
            return exceptions.TooManyRedirects

        if isinstance(exc, invalid_url):
            return exceptions.InvalidURL

        return None

    return classify


def _is_utf8(encoding: str) -> bool:
    "Whether the name means UTF-8, the encoding httpx sends. An unknown codec does not."
    try:
        return codecs.lookup(encoding).name == "utf-8"
    except LookupError:
        return False


def _check_supported(request: Request, backend: str, max_redirects: int):
    """Reject request options httpx cannot honor, instead of dropping them silently.

    Args:
        request (Request): The request about to be sent.
        backend (str): Name of the backend, for the exception.
        max_redirects (int): The client's redirect limit, reported when a request asks for another.

    Raises:
        UnsupportedRequestOption: One of the options is set and cannot be applied.
    """
    for option, hint in _UNSUPPORTED_HINTS.items():
        if getattr(request, option) is not None:
            raise UnsupportedRequestOption(backend, option, hint)

    # against the Request default, not the client's limit: a provided client picks its own, and
    # every request would fail against a number the caller never chose
    if request.allow_redirects and request.max_redirects != DEFAULT_MAX_REDIRECTS:
        raise UnsupportedRequestOption(
            backend,
            "max_redirects",
            f"The limit belongs to the client, and is {max_redirects} here. "
            f"Use the aiohttp backend for a per-request value.",
        )

    if request.auth is not None and (encoding := request.auth.get("encoding")) is not None and not _is_utf8(encoding):
        # httpx has nowhere to put another encoding
        raise UnsupportedRequestOption(
            backend,
            "auth.encoding",
            "Credentials are sent as UTF-8. Use the aiohttp backend for another encoding.",
        )


class BaseHttpxRequestContextManager(BaseRequestContextManager):
    """Context manager that executes a prepared HTTP request through an httpx-compatible client.

    Args:
        request (Request): The request to execute.
        client (HttpxClient): Client the request is sent with.
        max_body_size (int | None): Cap on the response body in bytes; ``None`` disables the cap.
        session_timeout (float | None): Budget for the whole response when the request sets none.
    """

    _binding: ClassVar[HttpxBinding]

    def __init__(
        self,
        request: Request,
        client: HttpxClient,
        max_body_size: int | None = None,
        session_timeout: float | None = None,
    ):
        super().__init__(request)
        # the two packages share the API the code below uses, and httpx names it for the type checker
        self._client = cast("AsyncClient", client)
        self._max_body_size = max_body_size
        self._session_timeout = session_timeout

    async def __aenter__(self) -> Response:
        """Send the request with httpx and convert the response to internal ``Response``."""
        deadline = deadline_for(self._request.timeout, self._session_timeout)
        with client_errors(self._binding.classify, self._request.url, self._request.method):
            async with within_deadline(deadline, self._request.url, self._request.method):
                return await self._send(deadline)

    async def _send(self, deadline: float | None) -> Response:
        if isinstance(self._request.data, dict):
            content, data = None, self._request.data
        else:
            content, data = self._request.data, None

        request = self._client.build_request(
            url=str(parse_url(self._request.url, self._request.params)),
            method=self._request.method,
            content=content,
            data=data,
            files=self._request.files,
            json=self._request.json_data,
            cookies=parse_cookies(self._request.cookies) if self._request.cookies is not None else None,
            headers=self._request.headers,
            # not truthiness: only the absence of a timeout falls back to the client
            timeout=self._request.timeout if self._request.timeout is not None else self._binding.use_client_default,
        )
        # without stream=True httpx buffers the whole body inside send(), before any limit applies
        response = await self._client.send(
            request,
            auth=(
                self._binding.basic_auth(
                    username=self._request.auth["username"], password=self._request.auth.get("password", "")
                )
                if self._request.auth is not None
                else self._binding.use_client_default
            ),
            follow_redirects=self._request.allow_redirects,
            stream=True,
        )
        self._exit_stack.push_async_callback(response.aclose)
        return Response(
            url=str(response.url),
            method=response.request.method,
            status=response.status_code,
            # httpx joins repeated headers on lookup, where aiohttp returns the first
            headers=CIMultiDictProxy(CIMultiDict(response.headers.multi_items())),
            cookies=to_simple_cookie(response.cookies),
            aiter_bytes=guard_stream(
                response.aiter_bytes,
                self._binding.classify,
                str(response.url),
                response.request.method,
                deadline,
            ),
            max_body_size=self._max_body_size,
        )


class BaseHttpxSession(BaseSession):
    """HTTP session implementation that wraps the ``AsyncClient`` of an httpx-compatible package.

    Args:
        timeout (float | None): Client-wide timeout in seconds.
        verify (SSLContext | bool): SSL handling passed to the client.
        proxy (str | dict[str, str | None] | None): Proxy URL, or a per-scheme mapping mounted on
            separate transports.
        max_body_size (int | None): Cap on a response body in bytes; ``None`` disables the cap.
        client (HttpxClient | None): Send through this client instead of creating one. Its own
            configuration is used as it is, which makes ``timeout``, ``verify``, ``proxy`` and the
            redirect limit inapplicable.
        owns_client (bool | None): Close ``client`` on :meth:`close`. Defaults to ``False`` for a
            provided client and ``True`` for one created here.

    Raises:
        ValueError: ``owns_client`` is ``False`` without a ``client``.
    """

    _binding: ClassVar[HttpxBinding]
    _context_manager: ClassVar[type[BaseHttpxRequestContextManager]]

    def __init__(
        self,
        *,
        timeout: float | None = None,
        verify: SSLContext | bool = True,
        proxy: str | dict[str, str | None] | None = None,
        max_body_size: int | None = None,
        client: HttpxClient | None = None,
        owns_client: bool | None = None,
    ):
        super().__init__(owns_client=resolve_client_ownership(client, owns_client))
        self._max_body_size = max_body_size
        # a provided client carries no total to take the budget from: httpx times each phase
        self._session_timeout = None if client is not None else timeout
        if client is not None:
            self._client = cast("AsyncClient", client)
            return

        if isinstance(proxy, dict):
            mounts = {
                scheme: self._binding.async_http_transport(proxy=proxy) for scheme, proxy in proxy.items() if proxy
            } or None
            proxy = None
        else:
            mounts = None

        # Pinned to the Request default so both backends follow the same number of
        # redirects; httpx would otherwise use its own default of 20.
        self._client = self._binding.async_client(
            timeout=timeout,
            verify=verify,
            proxy=proxy,
            mounts=mounts,
            max_redirects=DEFAULT_MAX_REDIRECTS,
        )

    def make_request(self, request: Request) -> BaseHttpxRequestContextManager:
        """Create a request context manager coupled with the shared client.

        Args:
            request (Request): The request to execute.

        Raises:
            UnsupportedRequestOption: The request sets an option httpx cannot honor per request.
        """
        _check_supported(request, self._binding.backend, self._client.max_redirects)
        return self._context_manager(request, self._client, self._max_body_size, self._session_timeout)

    async def _close_client(self):
        """Close the ``AsyncClient`` to free connectors and sockets."""
        await self._client.aclose()
