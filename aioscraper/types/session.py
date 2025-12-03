import json
from dataclasses import dataclass
from typing import MutableMapping, Any, Callable, Awaitable, TypedDict

from yarl import URL

from .._helpers.http import get_encoding

QueryParams = MutableMapping[str, str | int | float]
Cookies = MutableMapping[str, str]
Headers = MutableMapping[str, str]


class BasicAuth(TypedDict):
    username: str
    password: str


@dataclass(slots=True, kw_only=True)
class Request:
    """
    Represents an HTTP request with all its parameters.

    Args:
        url (str | URL): The target URL for the request
        method (str): HTTP method (GET, POST, etc.)
        params (QueryParams | None): URL query parameters
        data (Any): Request body data
        json_data (Any): JSON data to be sent in the request body
        cookies (Cookies | None): Request cookies
        headers (Headers | None): Request headers
        auth (BasicAuth | None): Basic authentication credentials
        proxy (str | None): Proxy URL
        timeout (float | None): Request timeout in seconds
        allow_redirects (bool): Whether to follow HTTP redirects
        max_redirects (int): Maximum number of redirects to follow

        priority (int): Priority of the request
        callback (Callable[..., Awaitable] | None): Async callback function to be called after successful request
        cb_kwargs (dict[str, Any] | None): Keyword arguments for the callback function
        errback (Callable[..., Awaitable] | None): Async error callback function
        settings (dict[str, Any] | None): Additional settings for the request
    """

    url: str
    method: str = "GET"
    params: QueryParams | None = None
    data: Any = None
    json_data: Any = None
    cookies: Cookies | None = None
    headers: Headers | None = None
    auth: BasicAuth | None = None
    proxy: str | None = None
    timeout: float | None = None
    allow_redirects: bool = True
    max_redirects: int = 10

    # not http params
    priority: int = 0
    callback: Callable[..., Awaitable[Any]] | None = None
    cb_kwargs: dict[str, Any] | None = None
    errback: Callable[..., Awaitable[Any]] | None = None
    settings: dict[str, Any] | None = None

    def build_url(self) -> URL:
        url = URL(self.url)
        if self.params:
            url.update_query(self.params)

        return url


SendRequest = Callable[[Request], Awaitable[None]]


class Response:
    "Represents an HTTP response with all its components"

    __slots__ = (
        "_url",
        "_method",
        "_status",
        "_headers",
        "_cookies",
        "_content",
    )

    def __init__(
        self,
        url: str,
        method: str,
        status: int,
        headers: Headers,
        cookies: Cookies,
        content: bytes,
    ) -> None:
        self._url = url
        self._method = method
        self._status = status
        self._headers = headers
        self._cookies = cookies
        self._content = content

    def __repr__(self) -> str:
        return f"Response[{self._method} {self.url}]"

    @property
    def url(self) -> str:
        return self._url

    @property
    def method(self) -> str:
        return self._method

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
    def ok(self) -> bool:
        "Returns ``True`` if ``status`` is less than ``400``, ``False`` if not"
        return 400 > self.status

    @property
    def content(self) -> bytes:
        return self._content

    def text(self, encoding: str | None = "utf-8", errors: str = "strict") -> str:
        "Read response payload and decode"
        if encoding is None:
            encoding = get_encoding(self.headers.get("Content-Type", ""))

        return self._content.decode(encoding, errors=errors)

    def json(
        self,
        *,
        encoding: str | None = None,
        loads: Callable[[str], Any] = json.loads,
    ) -> Any:
        "Read and decodes JSON response"
        stripped_content = self._content.strip()
        if not stripped_content:
            return None

        if encoding is None:
            encoding = get_encoding(self.headers.get("Content-Type", ""))

        return loads(stripped_content.decode(encoding))
