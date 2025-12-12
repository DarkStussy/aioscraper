import pytest

from aioscraper._helpers.func import compiled, get_func_kwargs
from aioscraper.types import Request, Response, SendRequest
from tests.mocks import MockAIOScraper


class Scraper:
    def __init__(self):
        self.results = {}

    async def __call__(self, send_request: SendRequest, dep: str):
        self.results["scraper_dep"] = dep
        await send_request(Request(url="https://api.test.com/deps", callback=self.parse))

    async def parse(self, response: Response, dep: str):
        self.results["response_dep"] = dep
        self.results["payload"] = await response.json()


@pytest.mark.asyncio
async def test_dependencies(mock_aioscraper: MockAIOScraper):
    response_data = {"status": "OK"}
    mock_aioscraper.server.add("https://api.test.com/deps", handler=lambda _: response_data)

    scraper = Scraper()

    mock_aioscraper(scraper)
    async with mock_aioscraper:
        mock_aioscraper.add_dependencies(dep="injected")
        await mock_aioscraper.wait()

    assert scraper.results["scraper_dep"] == "injected"
    assert scraper.results["response_dep"] == "injected"
    assert scraper.results["payload"] == response_data
    mock_aioscraper.server.assert_all_routes_handled()


def test_get_func_kwargs_picks_only_known_params():
    def fn(a, b, c): ...

    kwargs = get_func_kwargs(fn, a=1, b=2, c=3, d=4)

    assert kwargs == {"a": 1, "b": 2, "c": 3}


def test_get_func_kwargs_handles_missing_optional_params():
    def fn(a, b=2): ...

    kwargs = get_func_kwargs(fn, a=1, c=3)

    assert kwargs == {"a": 1}


@pytest.mark.asyncio
async def test_compiled_decorator_filters_kwargs():
    @compiled
    async def callback(a: int, b: str):
        return {"a": a, "b": b}

    result = await callback(a=1, b="test", c=3, d=4)

    assert result == {"a": 1, "b": "test"}


@pytest.mark.asyncio
async def test_compiled_decorator_sets_marker():
    @compiled
    async def callback():
        pass

    assert hasattr(callback, "__compiled__")
    assert callback.__compiled__ is True


@pytest.mark.asyncio
async def test_compiled_decorator_with_scraper(mock_aioscraper: MockAIOScraper):
    class CompiledScraper:
        def __init__(self):
            self.results = {}

        async def __call__(self, send_request: SendRequest):
            await send_request(Request(url="https://api.test.com/compiled", callback=self.parse))

        @compiled
        async def parse(self, response: Response, dep: str):
            self.results["dep"] = dep
            self.results["status"] = response.status

    mock_aioscraper.server.add("https://api.test.com/compiled", handler=lambda _: {"ok": True})

    scraper = CompiledScraper()
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        mock_aioscraper.add_dependencies(dep="optimized")
        await mock_aioscraper.wait()

    assert scraper.results["dep"] == "optimized"
    assert scraper.results["status"] == 200
