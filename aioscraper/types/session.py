import json
from dataclasses import dataclass, field
from http import HTTPMethod
from http.cookies import BaseCookie, Morsel, SimpleCookie
from typing import (
    Any,
    Awaitable,
    Callable,
    Mapping,
    MutableMapping,
    NamedTuple,
    NotRequired,
    TypedDict,
)

QueryParams = MutableMapping[str, str | int | float]
RequestCookies = MutableMapping[str, str | BaseCookie[str] | Morsel[Any]]
RequestHeaders = MutableMapping[str, str]
RequestFiles = MutableMapping[str, "File"]
ResponseHeaders = Mapping[str, str]

SendRequest = Callable[["Request"], Awaitable["Request"]]


class File(NamedTuple):
    name: str
    value: Any
    content_type: str | None = None


class BasicAuth(TypedDict):
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
        auth (BasicAuth | None): Basic authentication credentials
        proxy (str | None): Proxy URL (per-request proxies are honored only by the ``aiohttp`` backend)
        proxy_auth (BasicAuth | None): Proxy authentication credentials
        proxy_headers (RequestHeaders | None): Proxy headers
        timeout (float | None): Request timeout in seconds
        allow_redirects (bool): Whether to follow HTTP redirects
        max_redirects (int): Maximum number of redirects to follow

        delay (float | None): Delay before sending the request
        priority (int): Priority of the request
        callback (Callable[..., Awaitable] | None): Async callback function to be called after successful request
        cb_kwargs (dict[str, Any]): Keyword arguments for the callback function
        errback (Callable[..., Awaitable] | None): Async error callback function
        state (dict[str, Any]): State for middlewares
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
    max_redirects: int = 10

    # not http params
    delay: float | None = None
    priority: int = 0
    callback: Callable[..., Awaitable[Any]] | None = None
    cb_kwargs: dict[str, Any] = field(default_factory=dict)
    errback: Callable[..., Awaitable[Any]] | None = None
    state: dict[str, Any] = field(default_factory=dict)

    def clone(self) -> "Request":
        "Create a shallow copy of the request, suitable for retries and delayed scheduling."

        return Request(
            url=self.url,
            method=self.method,
            params={**self.params} if self.params is not None else None,
            data=self.data,
            json_data=self.json_data,
            files={**self.files} if self.files is not None else None,
            cookies={**self.cookies} if self.cookies is not None else None,
            headers={**self.headers} if self.headers is not None else None,
            auth=self.auth.copy() if self.auth is not None else None,
            proxy=self.proxy,
            proxy_auth=self.proxy_auth.copy() if self.proxy_auth is not None else None,
            proxy_headers={**self.proxy_headers} if self.proxy_headers is not None else None,
            timeout=self.timeout,
            allow_redirects=self.allow_redirects,
            max_redirects=self.max_redirects,
            delay=self.delay,
            priority=self.priority,
            callback=self.callback,
            cb_kwargs=self.cb_kwargs.copy(),
            errback=self.errback,
            state=self.state.copy(),
        )


@dataclass(slots=True, order=True)
class PRequest:
    "Priority Request Pair - for managing prioritized requests."

    priority: float
    request: Request = field(compare=False)


class Response:
    "Represents an HTTP response with all its components."

    __slots__ = ("_content", "_cookies", "_headers", "_method", "_read", "_status", "_url")

    def __init__(
        self,
        url: str,
        method: str,
        status: int,
        headers: ResponseHeaders,
        cookies: SimpleCookie,
        read: Callable[[], Awaitable[bytes]],
    ):
        self._url = url
        self._method = method
        self._status = status
        self._headers = headers
        self._cookies = cookies
        self._read = read
        self._content: bytes | None = None

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

    async def read(self) -> bytes:
        "Read response payload."
        if self._content is None:
            self._content = await self._read()

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
