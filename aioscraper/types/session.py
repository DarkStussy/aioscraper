import json
from dataclasses import dataclass
from typing import MutableMapping, Any, Callable, Awaitable, TypedDict, Protocol
from urllib.parse import parse_qsl, urlencode, urlparse

QueryParams = MutableMapping[str, str | int | float]

Cookies = MutableMapping[str, str]

Headers = MutableMapping[str, str]


class BasicAuth(TypedDict):
    username: str
    password: str


@dataclass(slots=True)
class Request:
    """
    Represents an HTTP request with all its parameters.

    Attributes:
        url (str): The target URL for the request
        method (str): HTTP method (GET, POST, etc.)
        params (QueryParams | None): URL query parameters
        data (Any): Request body data
        json_data (Any): JSON data to be sent in the request body
        cookies (Cookies | None): Request cookies
        headers (Headers | None): Request headers
        auth (BasicAuth | None): Basic authentication credentials
        proxy (str | None): Proxy URL
        timeout (float | None): Request timeout in seconds
    """

    url: str
    method: str
    params: QueryParams | None = None
    data: Any = None
    json_data: Any = None
    cookies: Cookies | None = None
    headers: Headers | None = None
    auth: BasicAuth | None = None
    proxy: str | None = None
    timeout: float | None = None

    @property
    def full_url(self) -> str:
        "Returns the complete URL including query parameters"

        if not self.params:
            return self.url

        url_parts = urlparse(self.url)
        return url_parts._replace(query=urlencode(dict(parse_qsl(url_parts.query)) | dict(self.params))).geturl()


@dataclass(slots=True)
class RequestParams:
    """
    Parameters for request callbacks and error handling.

    Attributes:
        callback (Callable[..., Awaitable] | None): Async callback function to be called after successful request
        cb_kwargs (dict[str, Any] | None): Keyword arguments for the callback function
        errback (Callable[..., Awaitable] | None): Async error callback function
        settings (dict[str, Any] | None): Additional settings for the request
    """

    callback: Callable[..., Awaitable[Any]] | None = None
    cb_kwargs: dict[str, Any] | None = None
    errback: Callable[..., Awaitable[Any]] | None = None
    settings: dict[str, Any] | None = None


class RequestSender(Protocol):
    """
    Protocol defining the interface for request senders.

    This protocol defines the required interface for classes that send HTTP requests.
    """

    async def __call__(
        self,
        url: str,
        method: str = "GET",
        callback: Callable[..., Awaitable[Any]] | None = None,
        cb_kwargs: dict[str, Any] | None = None,
        errback: Callable[..., Awaitable[Any]] | None = None,
        settings: dict[str, Any] | None = None,
        params: QueryParams | None = None,
        data: Any = None,
        json_data: Any = None,
        cookies: Cookies | None = None,
        headers: Headers | None = None,
        proxy: str | None = None,
        auth: BasicAuth | None = None,
        timeout: float | None = None,
        priority: int = 0,
    ) -> None: ...


class Response:
    """
    Represents an HTTP response with all its components.

    Attributes:
        url (str): The URL that was requested
        method (str): The HTTP method used
        params (QueryParams | None): Query parameters used in the request
        status (int): HTTP status code
        headers (Headers): Response headers
        cookies (Cookies): Response cookies
        content (bytes): Raw response content
        content_type (str | None): Content type of the response
    """

    __slots__ = (
        "_url",
        "_method",
        "_params",
        "_status",
        "_headers",
        "_cookies",
        "_content",
        "_content_type",
    )

    def __init__(
        self,
        url: str,
        method: str,
        params: QueryParams | None,
        status: int,
        headers: Headers,
        cookies: Cookies,
        content: bytes,
        content_type: str | None,
    ) -> None:
        self._url = url
        self._method = method
        self._params = params
        self._status = status
        self._headers = headers
        self._cookies = cookies
        self._content = content
        self._content_type = content_type

    def __repr__(self) -> str:
        return f"Response[{self._method} {self.full_url}]"

    @property
    def url(self) -> str:
        return self._url

    @property
    def full_url(self) -> str:
        if not self.params:
            return self.url

        url_parts = urlparse(self.url)
        return url_parts._replace(query=urlencode(dict(parse_qsl(url_parts.query)) | dict(self.params))).geturl()

    @property
    def method(self) -> str:
        return self._method

    @property
    def params(self) -> QueryParams | None:
        return self._params

    @property
    def status(self) -> int:
        return self._status

    @property
    def headers(self) -> Headers:
        return self._headers

    @property
    def cookies(self) -> Cookies:
        return self._cookies

    @property
    def content_type(self) -> str | None:
        return self._content_type

    @property
    def ok(self) -> bool:
        return 400 > self.status

    def bytes(self) -> bytes:
        return self._content

    def json(self) -> Any:
        return json.loads(self._content)

    def text(self, encoding: str = "utf-8") -> str:
        return self._content.decode(encoding)
