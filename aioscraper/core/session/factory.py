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
    """Structural stand-in for :class:`httpx.AsyncClient`, for the same reason as :class:`AiohttpClient`.

    An :class:`httpx2.AsyncClient` matches it as well: the fork carries the members named here.
    """

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

    try:
        from httpx2 import AsyncClient as AsyncClient2
    except ModuleNotFoundError:  # pragma: no cover
        pass
    else:
        if isinstance(client, AsyncClient2):
            from .httpx2 import Httpx2Session

            _reject_backend_mismatch(config, HttpBackend.HTTPX2)
            logger.info("Using the provided httpx2 client: %s", _IGNORED_FOR_PROVIDED_CLIENT)
            return lambda: Httpx2Session(client=client, max_body_size=config.max_response_body_size)

    raise AIOScraperException(
        f"Unsupported HTTP client {type(client).__name__}: expected aiohttp.ClientSession, "
        f"httpx.AsyncClient or httpx2.AsyncClient"
    )


def _log_session(backend: HttpBackend, config: SessionConfig):
    logger.info(
        "Using %s session: timeout=%.10gs, ssl=%s",
        backend,
        config.timeout,
        "configured" if config.ssl is not None else "default",
    )


def _httpx_sessionmaker(config: SessionConfig, session_cls: Callable[..., BaseSession]) -> SessionMaker:
    "Build the maker of an httpx-compatible session, whose constructors take the same arguments."
    return lambda: session_cls(
        timeout=config.timeout,
        verify=config.ssl,
        proxy=config.proxy,
        max_body_size=config.max_response_body_size,
    )


def get_sessionmaker(config: SessionConfig, client: HttpClient | None = None) -> SessionMaker:
    """Return a factory that builds a session using the chosen or available HTTP backend.

    Args:
        config (SessionConfig): Settings for the client and the limits the framework enforces.
        client (ClientSession | AsyncClient | None): An ``aiohttp``, ``httpx`` or ``httpx2`` client
            to send through instead of creating one. It selects the backend, is used as configured,
            and stays open when the run ends.

    Raises:
        AIOScraperException: No backend is installed, or ``client`` is of an unsupported type or
            contradicts ``config.http_backend``.
    """
    if client is not None:
        return _sessionmaker_for_client(config, client)

    if config.http_backend in (None, HttpBackend.AIOHTTP):
        try:
            from .aiohttp import AiohttpSession, ClientTimeout, TCPConnector

            _log_session(HttpBackend.AIOHTTP, config)
            return lambda: AiohttpSession(
                timeout=ClientTimeout(total=config.timeout),
                connector=TCPConnector(ssl=ssl) if (ssl := config.ssl) is not None else None,
                proxy=config.proxy if isinstance(config.proxy, str) else None,
                max_body_size=config.max_response_body_size,
            )
        except ModuleNotFoundError:  # pragma: no cover
            logger.debug("aiohttp not available, trying httpx")

    if config.http_backend in (None, HttpBackend.HTTPX):
        try:
            from .httpx import HttpxSession

            _log_session(HttpBackend.HTTPX, config)
            return _httpx_sessionmaker(config, HttpxSession)
        except ModuleNotFoundError:  # pragma: no cover
            logger.debug("httpx not available, trying httpx2")

    if config.http_backend in (None, HttpBackend.HTTPX2):
        try:
            from .httpx2 import Httpx2Session

            _log_session(HttpBackend.HTTPX2, config)
            return _httpx_sessionmaker(config, Httpx2Session)
        except ModuleNotFoundError:  # pragma: no cover
            logger.debug("httpx2 not available")

    logger.error("No HTTP backend available: aiohttp, httpx and httpx2 are not installed")
    raise AIOScraperException("aiohttp, httpx or httpx2 is not installed")
