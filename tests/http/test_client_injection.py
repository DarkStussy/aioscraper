import asyncio
from typing import AsyncIterator

import pytest
from aiohttp import ClientSession, ClientTimeout
from aiohttp.web import BaseRequest
from httpx import AsyncClient
from httpx2 import AsyncClient as AsyncClient2

from aioscraper import AIOScraper, Request, Response, ScheduleRequest
from aioscraper.config import Config, HttpBackend, SessionConfig
from aioscraper.core.session import BaseSession, get_sessionmaker
from aioscraper.core.session.aiohttp import AiohttpSession
from aioscraper.core.session.httpx import HttpxSession
from aioscraper.core.session.httpx2 import Httpx2Session
from aioscraper.exceptions import AIOScraperException
from tests.mocks import MockResponse, MockServer
from tests.mocks.client import patch_aiohttp, patch_httpx, patch_httpx2

URL = "https://api.test.com/data"


@pytest.fixture
async def aiohttp_server() -> AsyncIterator[MockServer]:
    async with MockServer(patch_aiohttp) as server:
        yield server


@pytest.fixture
async def httpx_server() -> AsyncIterator[MockServer]:
    async with MockServer(patch_httpx) as server:
        yield server


@pytest.fixture
async def httpx2_server() -> AsyncIterator[MockServer]:
    async with MockServer(patch_httpx2) as server:
        yield server


def _route(server: MockServer, seen: list[str | None]):
    def handler(request: BaseRequest) -> MockResponse:
        seen.append(request.headers.get("X-Token"))
        return MockResponse(json={"ok": True})

    server.add(URL, handler=handler)


async def _scrape(scraper: AIOScraper, bodies: list[dict]):
    @scraper
    async def run(schedule_request: ScheduleRequest):
        await schedule_request(Request(url=URL, callback=callback))

    async def callback(response: Response):
        bodies.append(await response.json())

    async with scraper:
        result = await scraper.wait()

    assert result.ok is True


async def test_injected_aiohttp_client_sends_and_stays_open(aiohttp_server: MockServer):
    seen: list[str | None] = []
    bodies: list[dict] = []
    _route(aiohttp_server, seen)

    async with ClientSession(headers={"X-Token": "abc"}) as client:
        await _scrape(AIOScraper(config=Config(), http_client=client), bodies)
        assert client.closed is False

    # the client's own defaults reach the server: aioscraper does not rebuild it
    assert seen == ["abc"]
    assert bodies == [{"ok": True}]


async def test_injected_httpx_client_sends_and_stays_open(httpx_server: MockServer):
    seen: list[str | None] = []
    bodies: list[dict] = []
    _route(httpx_server, seen)

    async with AsyncClient(headers={"X-Token": "abc"}) as client:
        await _scrape(AIOScraper(config=Config(), http_client=client), bodies)
        assert client.is_closed is False

    assert seen == ["abc"]
    assert bodies == [{"ok": True}]


async def test_injected_httpx2_client_sends_and_stays_open(httpx2_server: MockServer):
    seen: list[str | None] = []
    bodies: list[dict] = []
    _route(httpx2_server, seen)

    async with AsyncClient2(headers={"X-Token": "abc"}) as client:
        await _scrape(AIOScraper(config=Config(), http_client=client), bodies)
        assert client.is_closed is False

    assert seen == ["abc"]
    assert bodies == [{"ok": True}]


async def test_injected_aiohttp_client_can_disable_the_budget(aiohttp_server: MockServer):
    """aiohttp starts no timer for total=0, so it must not become a deadline that fires at once."""
    bodies: list[dict] = []

    async def handler(request: BaseRequest) -> MockResponse:
        await asyncio.sleep(0.05)
        return MockResponse(json={"ok": True})

    aiohttp_server.add(URL, handler=handler)

    async with ClientSession(timeout=ClientTimeout(total=0)) as client:
        await _scrape(AIOScraper(config=Config(), http_client=client), bodies)

    assert bodies == [{"ok": True}]


async def test_aiohttp_session_leaves_an_injected_client_open():
    async with ClientSession() as client:
        session = AiohttpSession(client=client)

        assert session.owns_client is False

        await session.close()

        assert client.closed is False


async def test_httpx_session_leaves_an_injected_client_open():
    async with AsyncClient() as client:
        session = HttpxSession(client=client)

        assert session.owns_client is False

        await session.close()

        assert client.is_closed is False


async def test_httpx2_session_leaves_an_injected_client_open():
    async with AsyncClient2() as client:
        session = Httpx2Session(client=client)

        assert session.owns_client is False

        await session.close()

        assert client.is_closed is False


async def test_ownership_of_an_injected_client_can_be_handed_over():
    client = ClientSession()
    session = AiohttpSession(client=client, owns_client=True)

    assert session.owns_client is True

    await session.close()

    assert client.closed is True


async def test_a_session_owns_the_client_it_creates():
    session = HttpxSession(timeout=1.0)

    assert session.owns_client is True

    await session.close()


@pytest.mark.parametrize("session_type", [AiohttpSession, HttpxSession, Httpx2Session])
def test_disowning_a_client_the_session_creates_is_rejected(session_type: type[BaseSession]):
    # nothing else could close it: a session never exposes the client it built
    with pytest.raises(ValueError, match="needs a client to disown"):
        session_type(owns_client=False)


async def test_the_client_selects_the_backend():
    async with ClientSession() as client:
        assert isinstance(get_sessionmaker(SessionConfig(), client=client)(), AiohttpSession)

    async with AsyncClient() as client:
        assert isinstance(get_sessionmaker(SessionConfig(), client=client)(), HttpxSession)

    async with AsyncClient2() as client:
        assert isinstance(get_sessionmaker(SessionConfig(), client=client)(), Httpx2Session)


async def test_a_client_contradicting_http_backend_is_rejected():
    async with ClientSession() as client:
        with pytest.raises(AIOScraperException, match="http_backend"):
            get_sessionmaker(SessionConfig(http_backend=HttpBackend.HTTPX), client=client)

    # the two httpx packages are separate backends, and one does not answer for the other
    async with AsyncClient() as client:
        with pytest.raises(AIOScraperException, match="http_backend"):
            get_sessionmaker(SessionConfig(http_backend=HttpBackend.HTTPX2), client=client)

    async with AsyncClient2() as client:
        with pytest.raises(AIOScraperException, match="http_backend"):
            get_sessionmaker(SessionConfig(http_backend=HttpBackend.HTTPX), client=client)


def test_an_unsupported_client_is_rejected():
    with pytest.raises(AIOScraperException, match="Unsupported HTTP client"):
        get_sessionmaker(SessionConfig(), client=object())  # type: ignore[reportArgumentType]


def test_http_client_and_sessionmaker_factory_are_mutually_exclusive():
    with pytest.raises(ValueError, match="mutually exclusive"):
        AIOScraper(http_client=object(), sessionmaker_factory=get_sessionmaker)  # type: ignore[reportArgumentType]
