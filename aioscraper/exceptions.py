class ClientException(Exception):
    "Base exception class for all client-related errors"

    ...


class HTTPException(ClientException):
    """
    Exception raised when an HTTP request fails with a specific status code.

    Attributes:
        status_code (int): The HTTP status code of the failed request
        message (str | None): Optional error message describing the failure
        url (str): The URL that was being accessed
        method (str): The HTTP method used for the request
    """

    def __init__(self, status_code: int, message: str | None, url: str, method: str) -> None:
        self.status_code = status_code
        self.message = message
        self.url = url
        self.method = method

    def __str__(self) -> str:
        return f"{self.method} {self.url}: {self.status_code}: {self.message}"


class RequestException(ClientException):
    """
    Exception raised when a request fails due to network or connection issues.

    Attributes:
        src (Exception | str): The original exception or error message that caused the failure
        url (str): The URL that was being accessed
        method (str): The HTTP method used for the request
    """

    def __init__(self, src: Exception | str, url: str, method: str) -> None:
        self.src = src
        self.url = url
        self.method = method

    def __str__(self) -> str:
        return f"[{self.src.__class__.__name__}]: {self.method} {self.url}: {self.src}"


class PipelineException(Exception):
    "Base exception class for all pipeline-related errors"

    ...
