from aioscraper.config import Config
from aioscraper.scraper import AIOScraper
from aioscraper.session.base import BaseSession
from aioscraper.session.factory import get_session
from aioscraper.types import Scraper

from .server import MockServer


class MockAIOScraper(AIOScraper):
    def __init__(self, *scrapers: Scraper, server: MockServer, client_type: str) -> None:
        super().__init__(*scrapers)
        self._server = server
        self._client_type = client_type

    @property
    def server(self) -> MockServer:
        return self._server

    def _create_session(self, config: Config) -> BaseSession:
        return get_session(config, self._client_type)
