import json
from http.cookies import BaseCookie, Morsel, SimpleCookie
from dataclasses import dataclass, field
from typing import Mapping, MutableMapping, Any, Callable, Awaitable, NotRequired, TypedDict

QueryParams = MutableMapping[str, str | int | float]
RequestCookies = MutableMapping[str, str | BaseCookie[str] | Morsel[Any]] | BaseCookie[str]
RequestHeaders = MutableMapping[str, str]
ResponseHeaders = Mapping[str, str]


class BasicAuth(TypedDict):
    username: str
    password: NotRequired[str]
    encoding: NotRequired[str]


@dataclass(slots=True, kw_only=True)
class Request:
    """
    Represents an HTTP request with all its parameters.

    Args:
        url (str | URL): Target URL
        method (str): HTTP method
        params (QueryParams | None): URL query parameters
        data (Any): Request body data
        json_data (Any): JSON data to be sent in the request body
        cookies (RequestCookies | None): Request cookies
        headers (RequestHeaders | None): Request headers
        auth (BasicAuth | None): Basic authentication credentials
        proxy (str | None): Proxy URL
        proxy_auth (BasicAuth | None): Proxy authentication credentials
        proxy_headers (RequestHeaders | None): Proxy headers
        timeout (float | None): Request timeout in seconds
        allow_redirects (bool): Whether to follow HTTP redirects
        max_redirects (int): Maximum number of redirects to follow

        priority (int): Priority of the request
        callback (Callable[..., Awaitable] | None): Async callback function to be called after successful request
        cb_kwargs (dict[str, Any] | None): Keyword arguments for the callback function
        errback (Callable[..., Awaitable] | None): Async error callback function
        state (dict[str, Any] | None): State for middlewares
    """

    url: str
    method: str = "GET"
    params: QueryParams | None = None
    data: Any = None
    json_data: Any = None
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
    priority: int = 0
    callback: Callable[..., Awaitable[Any]] | None = None
    cb_kwargs: dict[str, Any] = field(default_factory=dict)
    errback: Callable[..., Awaitable[Any]] | None = None
    state: dict[str, Any] = field(default_factory=dict)


SendRequest = Callable[[Request], Awaitable[Request]]


@dataclass(slots=True, frozen=True, kw_only=True)
class Response:
    """Represents an HTTP response with all its components.

    Args:
        url (str): Final URL of the response
        method (str): HTTP method used
        status (int): HTTP status code
        headers (ResponseHeaders): Response headers
        cookies (SimpleCookie): Parsed response cookies
        content (bytes): Raw response body
    """

    url: str
    method: str
    status: int
    headers: ResponseHeaders
    cookies: SimpleCookie
    content: bytes

    def __repr__(self) -> str:
        return f"Response[{self.method} {self.url}]"

    @property
    def ok(self) -> bool:
        "Returns ``True`` if ``status`` is less than ``400``, ``False`` if not"
        return 400 > self.status

    def text(self, encoding: str | None = "utf-8", errors: str = "strict") -> str:
        "Read response payload and decode"
        if encoding is None:
            encoding = self.get_encoding()

        return self.content.decode(encoding, errors=errors)

    def json(
        self,
        *,
        encoding: str | None = None,
        loads: Callable[[str], Any] = json.loads,
    ) -> Any:
        "Read and decodes JSON response"
        stripped_content = self.content.strip()
        if not stripped_content:
            return None

        if encoding is None:
            encoding = self.get_encoding()

        return loads(stripped_content.decode(encoding))

    def get_encoding(self) -> str:
        """
        Resolve response encoding from the ``Content-Type`` header.

        Returns:
            str: Detected charset or ``"utf-8"`` as a safe default.
        """
        content_type = self.headers.get("Content-Type", "")
        parts = content_type.split(";")
        params = parts[1:]
        items_to_strip = "\"' "

        for param in params:
            param = param.strip()
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
                    return value
                except LookupError:
                    return "utf-8"

        return "utf-8"
