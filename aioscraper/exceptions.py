from typing import Any, Mapping

from multidict import CIMultiDict, MultiMapping


class AIOScraperException(Exception):
    "Base scraper exception."


class ClientException(AIOScraperException):
    "Base exception class for all client-related errors."


class HTTPException(ClientException):
    """
    Exception raised when an HTTP request fails with a specific status code.

    Args:
        status_code (int): The HTTP status code of the failed request
        message (str): Error message describing the failure
        url (str): The URL that was being accessed
        method (str): The HTTP method used for the request
        headers (Mapping[str, str]): Response headers returned by the server
    """

    def __init__(self, url: str, method: str, status_code: int, headers: Mapping[str, str], message: str):
        self.url = url
        self.method = method
        self.status_code = status_code
        self.headers = headers
        self.message = message
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"{self.method} {self.url}: {self.status_code}: {self.message}"

    def __reduce__(self) -> tuple[Any, ...]:
        # aiohttp's CIMultiDictProxy does not pickle; its CIMultiDict does, and keeps the
        # duplicates and the case-insensitive lookup a plain dict would drop
        headers = CIMultiDict(self.headers.items()) if isinstance(self.headers, MultiMapping) else self.headers
        return (
            type(self),
            (self.url, self.method, self.status_code, headers, self.message),
            {**self.__dict__, "headers": headers},
        )


class _RequestFailure(ClientException):
    """
    Base for a failure the HTTP client reported for one request.

    Args:
        url (str): The URL that was being requested.
        method (str): The HTTP method used for the request.
        message (str): What the client reported.
    """

    def __init__(self, url: str, method: str, message: str):
        self.url = url
        self.method = method
        self.message = message
        super().__init__(str(self))

    def __str__(self) -> str:
        return f"{self.method} {self.url}: {self.message}"

    def __reduce__(self) -> tuple[Any, ...]:
        return type(self), (self.url, self.method, self.message), self.__dict__


class TransportError(_RequestFailure):
    """
    Raised when the HTTP client could not deliver a response.

    Every backend maps its own failures onto this hierarchy; the original is kept as ``__cause__``.
    """


class TransportTimeout(TransportError, TimeoutError):
    "Raised when the request ran out of time. Also a builtin ``TimeoutError``, as ``aiohttp`` raises."


class ConnectionFailed(TransportError):
    "Raised when the connection could not be established, or was lost before the response ended."


class DNSError(ConnectionFailed):
    "Raised when the host name could not be resolved."


class ProxyError(ConnectionFailed):
    "Raised when the proxy refused the connection or failed to establish the tunnel."


class TLSError(TransportError):
    "Raised when the TLS handshake failed. Not a :class:`ConnectionFailed`: it fails again the same way."


class TooManyRedirects(_RequestFailure):
    "Raised when the redirect chain outgrew the limit. Not a transport failure: the chain repeats."


class InvalidURL(_RequestFailure):
    "Raised when the client refused the URL: unparsable, or a scheme it does not speak."


class ResponseTooLarge(ClientException):
    """
    Raised when a response body exceeds the configured size limit.

    Args:
        url (str): The URL that returned the oversized body.
        method (str): The HTTP method used for the request.
        limit (int): Configured limit in bytes.
    """

    def __init__(self, url: str, method: str, limit: int):
        self.url = url
        self.method = method
        self.limit = limit
        super().__init__(f"{method} {url}: response body exceeds {limit} bytes")

    def __reduce__(self) -> tuple[Any, ...]:
        return type(self), (self.url, self.method, self.limit), self.__dict__


class StreamConsumed(ClientException):
    """
    Raised when a response body is read after its stream has been consumed.

    Args:
        url (str): The URL whose body was already consumed.
        method (str): The HTTP method used for the request.
    """

    def __init__(self, url: str, method: str):
        self.url = url
        self.method = method
        super().__init__(f"{method} {url}: response body has already been consumed")

    def __reduce__(self) -> tuple[Any, ...]:
        return type(self), (self.url, self.method), self.__dict__


class UnsupportedRequestOption(ClientException):
    """
    Raised when a request sets an option the selected HTTP backend cannot honor.

    Args:
        backend (str): Name of the HTTP backend that rejected the option.
        option (str): Name of the unsupported :class:`~aioscraper.types.Request` field.
        hint (str): Suggested way to achieve the same result.
    """

    def __init__(self, backend: str, option: str, hint: str):
        self.backend = backend
        self.option = option
        self.hint = hint
        super().__init__(f"The {backend} backend does not support Request.{option}. {hint}")

    def __reduce__(self) -> tuple[Any, ...]:
        return type(self), (self.backend, self.option, self.hint), self.__dict__


class PipelineException(AIOScraperException):
    "Base exception class for all pipeline-related errors."


class StopMiddlewareProcessing(AIOScraperException):
    "Stop further pipeline middlewares in the current phase (pre/post)."


class StopItemProcessing(AIOScraperException):
    "Raised by pipeline middlewares to stop processing the current item."


class InvalidRequestData(AIOScraperException):
    "Raised when request fields conflict, or carry a value no backend could send."


class CLIError(AIOScraperException):
    "Raised when CLI arguments are invalid or cannot be resolved."


class ConfigValidationError(AIOScraperException):
    "Raised when configuration validation fails."
