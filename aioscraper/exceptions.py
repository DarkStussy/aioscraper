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


class PipelineException(AIOScraperException):
    "Base exception class for all pipeline-related errors."


class StopMiddlewareProcessing(AIOScraperException):
    "Stop further middlewares in the current phase (inner/response/exception)."


class StopRequestProcessing(AIOScraperException):
    "Raised by middlewares to stop processing the current request entirely."


class StopItemProcessing(AIOScraperException):
    "Raised by pipeline middlewares to stop processing the current item."


class InvalidRequestData(AIOScraperException):
    "Raised when request payload fields conflict."


class CLIError(AIOScraperException):
    "Raised when CLI arguments are invalid or cannot be resolved."


class ConfigValidationError(AIOScraperException):
    "Raised when configuration validation fails."
