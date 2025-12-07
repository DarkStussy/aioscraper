import logging
from typing import Callable

from .base import BaseSession
from ...config import Config, HttpBackend
from ...exceptions import AIOScraperException

logger = logging.getLogger(__name__)


SessionMaker = Callable[[], BaseSession]
SessionMakerFactory = Callable[[Config], SessionMaker]


def get_sessionmaker(config: Config) -> SessionMaker:
    "Return a factory that builds a session using the chosen or available HTTP backend."
    if config.session.http_backend != HttpBackend.HTTPX:
        try:
            from .aiohttp import AiohttpSession, ClientTimeout, TCPConnector

            logger.info("use aiohttp session")
            return lambda: AiohttpSession(
                timeout=ClientTimeout(total=config.session.timeout),
                connector=TCPConnector(ssl=ssl) if (ssl := config.session.ssl) is not None else None,
                proxy=config.session.proxy if isinstance(config.session.proxy, str) else None,
            )
        except ModuleNotFoundError:  # pragma: no cover
            pass

    if config.session.http_backend != HttpBackend.AIOHTTP:
        try:
            from .httpx import HttpxSession

            logger.info("use httpx session")
            return lambda: HttpxSession(
                timeout=config.session.timeout, verify=config.session.ssl, proxy=config.session.proxy
            )
        except ModuleNotFoundError:  # pragma: no cover
            pass

    raise AIOScraperException("aiohttp or httpx is not installed")
