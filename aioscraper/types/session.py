import json
from dataclasses import dataclass, field
from http import HTTPMethod
from http.cookies import BaseCookie, Morsel, SimpleCookie
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Mapping,
    MutableMapping,
    NamedTuple,
    NotRequired,
    TypedDict,
)

from aioscraper.exceptions import ResponseTooLarge, StreamConsumed

QueryParams = MutableMapping[str, str | int | float]
RequestCookies = MutableMapping[str, str | BaseCookie[str] | Morsel[Any]]
RequestHeaders = MutableMapping[str, str]
RequestFiles = MutableMapping[str, "File"]
ResponseHeaders = Mapping[str, str]

SendRequest = Callable[["Request"], Awaitable["Request"]]

DEFAULT_MAX_REDIRECTS = 10
DEFAULT_CHUNK_SIZE = 65536
DEFAULT_MAX_ERROR_BODY_SIZE = 65536
# bounds what 64 concurrent bodies hold at 2 GiB, and no API payload reaches it by accident
DEFAULT_MAX_RESPONSE_BODY_SIZE = 32 * 1024 * 1024


class File(NamedTuple):
    name: str
    value: Any
    content_type: str | None = None


class BasicAuth(TypedDict):
    """Credentials for basic authentication.

    Args:
        username (str): User name.
        password (str): Password; empty when omitted.
        encoding (str): How to encode the credentials, Latin-1 by default. ``aiohttp`` only: the
            ``httpx`` backend always sends UTF-8, and raises
            :class:`~aioscraper.exceptions.UnsupportedRequestOption` for anything else. A name no
            codec answers to is rejected before the request is dispatched, as
            :class:`~aioscraper.exceptions.InvalidRequestData`.
    """

    username: str
    password: NotRequired[str]
    encoding: NotRequired[str]


@dataclass(slots=True, kw_only=True)
class Request:
    """
    Represents an HTTP request with all its parameters.

    Args:
        url (str): Target URL
        method (str): HTTP method
        params (QueryParams | None): URL query parameters
        data (Any): Request body data
        files (RequestFiles | None): Multipart files mapping
        json_data (Any): JSON data to be sent in the request body
        cookies (RequestCookies | None): Request cookies
        headers (RequestHeaders | None): Request headers
        auth (BasicAuth | None): Basic authentication credentials. ``httpx`` sends them as UTF-8
            and rejects any other ``encoding``
        proxy (str | None): Proxy URL. ``aiohttp`` only; the ``httpx`` backend raises
            :class:`~aioscraper.exceptions.UnsupportedRequestOption`
        proxy_auth (BasicAuth | None): Proxy authentication credentials. ``aiohttp`` only
        proxy_headers (RequestHeaders | None): Proxy headers. ``aiohttp`` only
        timeout (float | None): Request timeout in seconds, positive; ``None`` uses the session's.
            Anything else raises :class:`~aioscraper.exceptions.InvalidRequestData`
        allow_redirects (bool): Whether to follow HTTP redirects
        max_redirects (int): Maximum number of redirects to follow. Only ``aiohttp`` accepts a
            per-request value; on ``httpx`` the limit is the client's, so any value other than the
            default here is rejected

        delay (float | None): Delay before sending the request
        retryable (bool | None): Overrides the retry policy's method check; ``None`` defers to
            :attr:`RequestRetryConfig.methods <aioscraper.config.models.RequestRetryConfig.methods>`
        priority (int): Priority of the request
        callback (Callable[..., Awaitable] | None): Async callback function to be called after successful request
        cb_kwargs (dict[str, Any]): Keyword arguments for the callback function
        errback (Callable[..., Awaitable] | None): Async error callback function
        state (dict[str, Any]): Free-form bag for middlewares and callbacks, shared by every send
            of this object. The framework never writes to it
    """

    url: str
    method: str = HTTPMethod.GET
    params: QueryParams | None = None
    data: Any = None
    json_data: Any = None
    files: RequestFiles | None = None
    cookies: RequestCookies | None = None
    headers: RequestHeaders | None = None
    auth: BasicAuth | None = None
    proxy: str | None = None
    proxy_auth: BasicAuth | None = None
    proxy_headers: RequestHeaders | None = None
    timeout: float | None = None
    allow_redirects: bool = True
    max_redirects: int = DEFAULT_MAX_REDIRECTS

    # not http params
    delay: float | None = None
    retryable: bool | None = None
    priority: int = 0
    callback: Callable[..., Awaitable[Any]] | None = None
    cb_kwargs: dict[str, Any] = field(default_factory=dict)
    errback: Callable[..., Awaitable[Any]] | None = None
    state: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True, order=True)
class Attempt:
    """One admission-to-dispatch cycle of a request.

    Everything the framework tracks per attempt lives here rather than on ``Request``: the same
    request object can be sent more than once, and a retry admits a new attempt of it.

    Attributes:
        priority (float): Ordering key; a timestamp for delayed requests.
        request (Request): The request to send.
        holds_slot (bool): Whether this entry reserved a scheduler admission slot.
        retries (int): How many times this request was already re-admitted by the retry policy.
    """

    priority: float
    request: Request = field(compare=False)
    holds_slot: bool = field(default=False, compare=False)
    retries: int = field(default=0, compare=False)


class Response:
    """
    Represents an HTTP response with all its components.

    The body is streamed from the connection, which the backend closes once the middleware
    chain and the callback return, so it has to be read inside the callback.

    Args:
        url (str): Final URL of the response.
        method (str): HTTP method used.
        status (int): HTTP status code.
        headers (ResponseHeaders): Response headers.
        cookies (SimpleCookie): Parsed response cookies.
        aiter_bytes (Callable[[int], AsyncIterator[bytes]]): Backend body iterator, taking a chunk size.
        max_body_size (int | None): Cap on the body in bytes; ``None`` disables the cap.
    """

    __slots__ = (
        "_aiter_bytes",
        "_content",
        "_cookies",
        "_headers",
        "_max_body_size",
        "_method",
        "_status",
        "_streamed",
        "_url",
    )

    def __init__(
        self,
        url: str,
        method: str,
        status: int,
        headers: ResponseHeaders,
        cookies: SimpleCookie,
        aiter_bytes: Callable[[int], AsyncIterator[bytes]],
        max_body_size: int | None = None,
    ):
        self._url = url
        self._method = method
        self._status = status
        self._headers = headers
        self._cookies = cookies
        self._aiter_bytes = aiter_bytes
        self._max_body_size = max_body_size
        self._content: bytes | None = None
        self._streamed = False

    @property
    def url(self) -> str:
        "Final URL of the response."
        return self._url

    @property
    def method(self) -> str:
        "HTTP method used."
        return self._method

    @property
    def status(self) -> int:
        "HTTP status code."
        return self._status

    @property
    def headers(self) -> ResponseHeaders:
        "Response headers."
        return self._headers

    @property
    def cookies(self) -> SimpleCookie:
        "Parsed response cookies."
        return self._cookies

    @property
    def ok(self) -> bool:
        "Returns ``True`` if ``status`` is less than ``400``, ``False`` if not"
        return self._status < 400  # noqa: PLR2004

    def __repr__(self) -> str:
        return f"Response[{self._method} {self._url}]"

    def _consume(self):
        if self._streamed:
            raise StreamConsumed(self._url, self._method)

        self._streamed = True

    async def _read_limited(self, limit: int) -> bytes:
        # bounded by the caller alone: the error path budgets the body it needs for a message
        # regardless of max_body_size, which bounds what a callback may receive
        if limit <= 0:
            return b""

        self._consume()
        chunks: list[bytes] = []
        size = 0
        async for chunk in self._aiter_bytes(min(limit, DEFAULT_CHUNK_SIZE)):
            chunks.append(chunk)
            size += len(chunk)
            if size >= limit:
                break

        return b"".join(chunks)[:limit]

    async def iter_bytes(self, chunk_size: int = DEFAULT_CHUNK_SIZE) -> AsyncIterator[bytes]:
        """
        Stream the response payload chunk by chunk.

        Breaking out of the loop early is allowed; the connection is released when the request
        context closes. A body already buffered by :meth:`read` is replayed from memory.

        Args:
            chunk_size (int): Maximum size of a single chunk in bytes.

        Yields:
            bytes: Next chunk of the body.

        Raises:
            ResponseTooLarge: The body exceeds ``max_body_size``.
            StreamConsumed: The stream has already been consumed.
        """
        if self._content is not None:
            for start in range(0, len(self._content), chunk_size):
                yield self._content[start : start + chunk_size]

            return

        self._consume()
        size = 0
        async for chunk in self._aiter_bytes(chunk_size):
            size += len(chunk)
            if self._max_body_size is not None and size > self._max_body_size:
                raise ResponseTooLarge(self._url, self._method, self._max_body_size)

            yield chunk

    async def read(self, *, limit: int | None = None) -> bytes:
        """
        Read response payload.

        An unlimited read buffers the body and can be repeated; a limited read consumes the
        stream without buffering, so it cannot be followed by another read.

        Args:
            limit (int | None): Read at most this many bytes, itself capped by ``max_body_size``;
                ``None`` reads the whole body.

        Returns:
            bytes: The body, truncated to the effective limit when one is given.

        Raises:
            ResponseTooLarge: The body exceeds ``max_body_size``; only an unlimited read can hit it.
            StreamConsumed: The stream has already been consumed.
        """
        if self._content is not None:
            return self._content if limit is None else self._content[:limit]

        if limit is not None:
            if self._max_body_size is not None:
                limit = min(limit, self._max_body_size)

            return await self._read_limited(limit)

        content = bytearray()
        async for chunk in self.iter_bytes():
            content += chunk

        self._content = bytes(content)
        return self._content

    async def text(self, encoding: str | None = "utf-8", errors: str = "strict") -> str:
        "Read response payload and decode."
        if encoding is None:
            encoding = self.get_encoding()

        content = await self.read()
        return content.decode(encoding, errors=errors)

    async def json(self, *, encoding: str | None = None, loads: Callable[[str], Any] = json.loads) -> Any:
        "Read and decodes JSON response."
        content = await self.read()

        stripped_content = content.strip()
        if not stripped_content:
            return None

        if encoding is None:
            encoding = self.get_encoding()

        return loads(stripped_content.decode(encoding))

    def get_encoding(self) -> str:
        """
        Resolve response encoding from the ``Content-Type`` header.

        Parses the Content-Type header for a charset parameter. Returns "utf-8"
        as a safe default if no charset is found or if the charset is invalid.

        Returns:
            str: Detected charset or ``"utf-8"`` as a safe default.
        """
        content_type = self.headers.get("Content-Type", "")
        parts = content_type.split(";")
        params = [param.strip() for param in parts[1:]]
        items_to_strip = "\"' "

        for param in params:
            if not param:
                continue

            if "=" not in param:
                continue

            key, value = param.split("=", 1)
            key = key.strip(items_to_strip).lower()
            value = value.strip(items_to_strip)

            if key == "charset":
                try:
                    "".encode(value)
                except LookupError:
                    return "utf-8"
                else:
                    return value

        return "utf-8"
