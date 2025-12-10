from typing import AsyncIterator

import pytest

from tests.mocks import MockAIOScraper, MockServer, client

HTTP_BACKENDS = ("aiohttp", "httpx")


@pytest.fixture(params=HTTP_BACKENDS, ids=HTTP_BACKENDS)
async def mock_aioscraper(request: pytest.FixtureRequest) -> AsyncIterator[MockAIOScraper]:
    patch_client = client.patch_httpx if request.param == "httpx" else client.patch_aiohttp
    async with MockServer(patch_client) as server:
        yield MockAIOScraper(server=server, http_backend=request.param)
