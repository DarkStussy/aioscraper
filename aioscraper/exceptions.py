from typing import Mapping


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

    def __str__(self) -> str:
        return f"{self.method} {self.url}: {self.status_code}: {self.message}"


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


class PipelineException(AIOScraperException):
    "Base exception class for all pipeline-related errors."


class StopMiddlewareProcessing(AIOScraperException):
    "Stop further pipeline middlewares in the current phase (pre/post)."


class StopItemProcessing(AIOScraperException):
    "Raised by pipeline middlewares to stop processing the current item."


class InvalidRequestData(AIOScraperException):
    "Raised when request payload fields conflict."


class CLIError(AIOScraperException):
    "Raised when CLI arguments are invalid or cannot be resolved."


class ConfigValidationError(AIOScraperException):
    "Raised when configuration validation fails."
