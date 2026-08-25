import pytest

from aioscraper import AIOScraper
from aioscraper._helpers.deps import CALLBACK_ARGUMENTS, RESERVED_DEPENDENCIES
from aioscraper._helpers.func import compiled, get_func_kwargs
from aioscraper.types import Request, Response, ScheduleRequest
from tests.mocks import MockAIOScraper


class Scraper:
    def __init__(self):
        self.results = {}

    async def __call__(self, schedule_request: ScheduleRequest, dep: str):
        self.results["scraper_dep"] = dep
        await schedule_request(Request(url="https://api.test.com/deps", callback=self.parse))

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


@pytest.mark.parametrize("name", sorted(RESERVED_DEPENDENCIES))
def test_add_dependencies_rejects_a_reserved_name(name: str):
    with pytest.raises(ValueError, match=f"Dependency names reserved by the framework: {name}"):
        AIOScraper().add_dependencies(**{name: "registered"})


@pytest.mark.asyncio
async def test_config_stays_overridable(mock_aioscraper: MockAIOScraper):
    captured = {}

    async def scraper(config: object = None):
        captured["config"] = config

    mock_aioscraper(scraper)
    async with mock_aioscraper:
        mock_aioscraper.add_dependencies(config="registered")
        await mock_aioscraper.wait()

    assert captured["config"] == "registered"


@pytest.mark.asyncio
async def test_a_reserved_name_written_into_the_mapping_fails_the_start(mock_aioscraper: MockAIOScraper):
    """add_dependencies is not the only way in: dependencies is a public attribute."""
    mock_aioscraper.dependencies["pipeline"] = "registered"
    seen = []

    @mock_aioscraper.pipeline.global_middleware
    def factory(pipeline: object):
        seen.append(pipeline)
        raise AssertionError("the factory must not run")

    with pytest.raises(ValueError, match="Dependency names reserved by the framework: pipeline"):
        async with mock_aioscraper:
            await mock_aioscraper.wait()

    # the factories are built before the executor, so the check cannot live there alone
    assert not seen


@pytest.mark.parametrize("name", sorted(CALLBACK_ARGUMENTS))
def test_cb_kwargs_rejects_a_callback_argument(name: str):
    with pytest.raises(ValueError, match=f"cb_kwargs names reserved by the framework: {name}"):
        Request("https://api.test.com/deps", cb_kwargs={name: "mine"})


@pytest.mark.asyncio
async def test_cb_kwargs_wins_over_a_dependency(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/deps", handler=lambda _: {})
    captured = {}

    async def parse(dep: str):
        captured["dep"] = dep

    async def scraper(schedule_request: ScheduleRequest):
        await schedule_request(
            Request("https://api.test.com/deps", callback=parse, cb_kwargs={"dep": "per-request"}),
        )

    mock_aioscraper(scraper)
    async with mock_aioscraper:
        mock_aioscraper.add_dependencies(dep="global")
        await mock_aioscraper.wait()

    assert captured["dep"] == "per-request"


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

        async def __call__(self, schedule_request: ScheduleRequest):
            await schedule_request(Request(url="https://api.test.com/compiled", callback=self.parse))

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
