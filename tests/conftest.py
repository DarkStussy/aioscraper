from typing import AsyncIterator

import pytest

from tests.mocks import MockServer, MockAIOScraper
from tests.mocks import client

CLIENTS = ("aiohttp", "httpx")


@pytest.fixture(params=CLIENTS, ids=CLIENTS)
async def mock_aioscraper(request: pytest.FixtureRequest) -> AsyncIterator[MockAIOScraper]:
    if request.param == "httpx":
        patch_client = client.patch_httpx
    else:
        patch_client = client.patch_aiohttp

    async with MockServer(patch_client) as server:
        yield MockAIOScraper(server=server, client_type=request.param)
