import json
from dataclasses import dataclass
from typing import Union, Mapping, Any, Callable, Awaitable, TypedDict, Protocol
from urllib.parse import urlencode

QueryParams = Mapping[str, Union[str, int, float]]

Cookies = Mapping[str, str]

Headers = Mapping[str, str]


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
        return f"{self.url}{urlencode(self.params or {})}"


@dataclass(slots=True)
class RequestParams:
    """
    Parameters for request callbacks and error handling.

    Attributes:
        callback (Callable[..., Awaitable] | None): Async callback function to be called after successful request
        cb_kwargs (dict[str, Any] | None): Keyword arguments for the callback function
        errback (Callable[..., Awaitable] | None): Async error callback function
    """

    callback: Callable[..., Awaitable] | None = None
    cb_kwargs: dict[str, Any] | None = None
    errback: Callable[..., Awaitable] | None = None


class RequestSender(Protocol):
    """
    Protocol defining the interface for request senders.

    This protocol defines the required interface for classes that send HTTP requests.
    """

    async def __call__(
        self,
        url: str,
        method: str = "GET",
        callback: Callable[..., Awaitable] | None = None,
        cb_kwargs: dict[str, Any] | None = None,
        errback: Callable[..., Awaitable] | None = None,
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

    @property
    def url(self) -> str:
        return self._url

    @property
    def full_url(self) -> str:
        return f"{self.url}{urlencode(self.params or {})}"

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

    def bytes(self) -> bytes:
        return self._content

    def json(self) -> Any:
        return json.loads(self._content)

    def text(self, encoding: str = "utf-8") -> str:
        return self._content.decode(encoding)
