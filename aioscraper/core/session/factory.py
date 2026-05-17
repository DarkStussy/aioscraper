import logging
from typing import Callable

from aioscraper.config import HttpBackend, SessionConfig
from aioscraper.exceptions import AIOScraperException

from .base import BaseSession

logger = logging.getLogger(__name__)


SessionMaker = Callable[[], BaseSession]
SessionMakerFactory = Callable[[SessionConfig], SessionMaker]


def get_sessionmaker(config: SessionConfig) -> SessionMaker:
    "Return a factory that builds a session using the chosen or available HTTP backend."
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
            )
        except ModuleNotFoundError:  # pragma: no cover
            logger.debug("httpx not available")

    logger.error("No HTTP backend available: aiohttp and httpx are not installed")
    raise AIOScraperException("aiohttp or httpx is not installed")
