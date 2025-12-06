from aioscraper.config import Config
from aioscraper.scraper import AIOScraper
from aioscraper.session.factory import SessionMaker, get_sessionmaker
from aioscraper.types import Scraper

from .server import MockServer


class MockAIOScraper(AIOScraper):
    def __init__(self, *scrapers: Scraper, server: MockServer, http_backend: str):
        super().__init__(*scrapers)
        self._server = server
        self._http_backend = http_backend

    @property
    def server(self) -> MockServer:
        return self._server

    def _get_sessionmaker(self, config: Config) -> SessionMaker:
        return get_sessionmaker(config, self._http_backend)
