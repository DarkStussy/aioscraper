import asyncio
import sys
from typing import AsyncIterator, Iterator

import pytest

from tests.mocks import MockAIOScraper, MockServer, client

HTTP_BACKENDS = ("aiohttp", "httpx")

# pytest-asyncio saves the current loop with asyncio.get_event_loop(), which before 3.14
# creates one that nobody closes. Owning it here keeps that ResourceWarning out of the session.
_OWNED_LOOP = asyncio.new_event_loop() if sys.version_info < (3, 14) else None


def pytest_configure(config: pytest.Config):
    if _OWNED_LOOP is not None:
        asyncio.set_event_loop(_OWNED_LOOP)


def pytest_unconfigure(config: pytest.Config):
    if _OWNED_LOOP is not None:
        asyncio.set_event_loop(None)
        _OWNED_LOOP.close()


@pytest.fixture(autouse=True)
def _keep_current_event_loop() -> Iterator[None]:
    "asyncio.run() unsets the current loop, so restore it before the next test sets up."
    yield
    if _OWNED_LOOP is not None:
        asyncio.set_event_loop(_OWNED_LOOP)


@pytest.fixture(params=HTTP_BACKENDS, ids=HTTP_BACKENDS)
async def mock_aioscraper(request: pytest.FixtureRequest) -> AsyncIterator[MockAIOScraper]:
    patch_client = client.patch_httpx if request.param == "httpx" else client.patch_aiohttp
    async with MockServer(patch_client) as server:
        yield MockAIOScraper(server=server, http_backend=request.param)
