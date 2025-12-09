from aioscraper.config import Config
from aioscraper.core import AIOScraper
from aioscraper.types import Scraper

from .server import MockServer


class MockAIOScraper(AIOScraper):
    def __init__(self, *scrapers: Scraper, server: MockServer, http_backend: str):
        super().__init__(*scrapers, config=Config())
        self._server = server
        self._http_backend = http_backend

    @property
    def server(self) -> MockServer:
        return self._server

    async def wait(self):
        object.__setattr__(self.config.session, "http_backend", self._http_backend)
        await super().wait()
