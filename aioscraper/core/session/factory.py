import logging
from typing import Any, Callable, Protocol

from aioscraper.config import HttpBackend, SessionConfig
from aioscraper.exceptions import AIOScraperException

from .base import BaseSession


class AiohttpClient(Protocol):
    """Structural stand-in for :class:`aiohttp.ClientSession`, listing the members the session uses.

    Naming the class itself would leave the alias unresolved in an install without aiohttp, and
    ``py.typed`` carries that into the type checker of the project using it.
    """

    request: Callable[..., Any]
    close: Callable[..., Any]


class HttpxClient(Protocol):
    "Structural stand-in for :class:`httpx.AsyncClient`, for the same reason as :class:`AiohttpClient`."

    build_request: Callable[..., Any]
    send: Callable[..., Any]
    aclose: Callable[..., Any]


HttpClient = AiohttpClient | HttpxClient

logger = logging.getLogger(__name__)


SessionMaker = Callable[[], BaseSession]
SessionMakerFactory = Callable[[SessionConfig], SessionMaker]

# a provided client is used as configured, so nothing that builds one can be applied to it
_IGNORED_FOR_PROVIDED_CLIENT = "timeout, ssl and proxy settings are not applied"


def _reject_backend_mismatch(config: SessionConfig, backend: HttpBackend):
    if config.http_backend is not None and config.http_backend != backend:
        raise AIOScraperException(
            f"http_backend is set to {config.http_backend}, but the provided client is a {backend} one"
        )


def _sessionmaker_for_client(config: SessionConfig, client: HttpClient) -> SessionMaker:
    "Wrap a client the caller owns, leaving it open when the scraper closes its session."
    try:
        from aiohttp import ClientSession
    except ModuleNotFoundError:  # pragma: no cover
        pass
    else:
        if isinstance(client, ClientSession):
            from .aiohttp import AiohttpSession

            _reject_backend_mismatch(config, HttpBackend.AIOHTTP)
            logger.info("Using the provided aiohttp client: %s", _IGNORED_FOR_PROVIDED_CLIENT)
            return lambda: AiohttpSession(client=client, max_body_size=config.max_response_body_size)

    try:
        from httpx import AsyncClient
    except ModuleNotFoundError:  # pragma: no cover
        pass
    else:
        if isinstance(client, AsyncClient):
            from .httpx import HttpxSession

            _reject_backend_mismatch(config, HttpBackend.HTTPX)
            logger.info("Using the provided httpx client: %s", _IGNORED_FOR_PROVIDED_CLIENT)
            return lambda: HttpxSession(client=client, max_body_size=config.max_response_body_size)

    raise AIOScraperException(
        f"Unsupported HTTP client {type(client).__name__}: expected aiohttp.ClientSession or httpx.AsyncClient"
    )


def get_sessionmaker(config: SessionConfig, client: HttpClient | None = None) -> SessionMaker:
    """Return a factory that builds a session using the chosen or available HTTP backend.

    Args:
        config (SessionConfig): Settings for the client and the limits the framework enforces.
        client (ClientSession | AsyncClient | None): Send through this client instead of creating
            one. It selects the backend, is used as configured, and stays open when the run ends.

    Raises:
        AIOScraperException: No backend is installed, or ``client`` is of an unsupported type or
            contradicts ``config.http_backend``.
    """
    if client is not None:
        return _sessionmaker_for_client(config, client)

    if config.http_backend != HttpBackend.HTTPX:
        try:
            from .aiohttp import AiohttpSession, ClientTimeout, TCPConnector

            logger.info(
                "Using aiohttp session: timeout=%.10gs, ssl=%s",
                config.timeout,
                "configured" if config.ssl is not None else "default",
            )
            return lambda: AiohttpSession(
                timeout=ClientTimeout(total=config.timeout),
                connector=TCPConnector(ssl=ssl) if (ssl := config.ssl) is not None else None,
                proxy=config.proxy if isinstance(config.proxy, str) else None,
                max_body_size=config.max_response_body_size,
            )
        except ModuleNotFoundError:  # pragma: no cover
            logger.debug("aiohttp not available, trying httpx")

    if config.http_backend != HttpBackend.AIOHTTP:
        try:
            from .httpx import HttpxSession

            logger.info(
                "Using httpx session: timeout=%.10gs, ssl=%s",
                config.timeout,
                "configured" if config.ssl is not None else "default",
            )
            return lambda: HttpxSession(
                timeout=config.timeout,
                verify=config.ssl,
                proxy=config.proxy,
                max_body_size=config.max_response_body_size,
            )
        except ModuleNotFoundError:  # pragma: no cover
            logger.debug("httpx not available")

    logger.error("No HTTP backend available: aiohttp and httpx are not installed")
    raise AIOScraperException("aiohttp or httpx is not installed")
