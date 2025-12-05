from aioscraper.config import Config
from aioscraper.scraper import AIOScraper, Lifespan
from aioscraper.session.aiohttp import AiohttpSession, ClientTimeout, TCPConnector
from aioscraper.session.base import BaseSession
from aioscraper.session.httpx import HttpxSession
from aioscraper.types import Scraper

from .server import MockServer


class MockAIOScraper(AIOScraper):
    def __init__(
        self,
        *scrapers: Scraper,
        server: MockServer,
        client_type: str,
        lifespan: Lifespan | None = None,
    ) -> None:
        super().__init__(*scrapers, lifespan=lifespan)
        self._server = server
        self._client_type = client_type

    @property
    def server(self) -> MockServer:
        return self._server

    def set_lifespan(self, lifespan: Lifespan) -> None:
        self._lifespan = lifespan

    def _create_session(self, config: Config) -> BaseSession:
        if self._client_type == "httpx":
            return HttpxSession(timeout=config.session.timeout, verify=config.session.ssl)

        return AiohttpSession(
            timeout=ClientTimeout(total=config.session.timeout),
            connector=TCPConnector(ssl=ssl) if (ssl := config.session.ssl) is not None else None,
        )
