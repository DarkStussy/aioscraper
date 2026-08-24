from dataclasses import replace

from aioscraper.config import Config, RequestRetryConfig
from aioscraper.core import AIOScraper
from aioscraper.core.errors import RunResult
from aioscraper.types import Scraper

from .server import MockServer

_NO_RETRIES = RequestRetryConfig(enabled=False)


class MockAIOScraper(AIOScraper):
    def __init__(self, *scrapers: Scraper, server: MockServer, http_backend: str):
        super().__init__(*scrapers, config=Config())
        self._server = server
        self._http_backend = http_backend

    @property
    def server(self) -> MockServer:
        return self._server

    async def wait(self, timeout: float | None = None) -> RunResult:
        # rebuilt rather than mutated: SessionConfig() is the shared default of every Config()
        session = replace(self.config.session, http_backend=self._http_backend)
        # a test that says nothing about retries is asserting one attempt
        if session.retry == RequestRetryConfig():
            session = replace(session, retry=_NO_RETRIES)

        self.config = replace(self.config, session=session)
        return await super().wait(timeout)
