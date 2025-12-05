from typing import Callable
import pytest
from dataclasses import dataclass

from aioscraper.config import PipelineConfig
from aioscraper.exceptions import PipelineException
from aioscraper.holders.pipeline import PipelineMiddlewareType
from aioscraper.types import Pipeline, Request, SendRequest, Response, ItemType, PipelineMiddleware
from aioscraper.pipeline import BasePipeline
from aioscraper.pipeline.dispatcher import PipelineContainer, PipelineDispatcher

from .mocks import MockAIOScraper, MockResponse


@dataclass
class Item:
    pipeline_name: str
    is_processed: bool = False
    from_pre: bool = False


class RealPipeline(BasePipeline[Item]):
    def __init__(self, *labels: str) -> None:
        self.items: list[Item] = []
        self.closed = False
        self.labels = labels

    async def put_item(self, item: Item) -> Item:
        self.items.append(item)
        return item

    async def close(self) -> None:
        self.closed = True


async def pre_processing_middleware(item: Item) -> Item:
    assert item.pipeline_name == "test"
    item.from_pre = True
    return item


async def post_processing_middleware(item: Item) -> Item:
    assert item.pipeline_name == "test"
    item.is_processed = True
    return item


class Scraper:
    async def __call__(self, send_request: SendRequest) -> None:
        await send_request(Request(url="https://api.test.com/v1", callback=self.parse))

    async def parse(self, response: Response, pipeline: Pipeline) -> None:
        await pipeline(Item(response.text()))


def register_via_decorator(
    scraper: MockAIOScraper,
    middleware_type: PipelineMiddlewareType,
    name: str,
    middleware: PipelineMiddleware[ItemType],
):
    scraper.pipeline.middleware(middleware_type, name)(middleware)


def register_via_add(
    scraper: MockAIOScraper,
    middleware_type: PipelineMiddlewareType,
    name: str,
    middleware: PipelineMiddleware[Item],
):
    scraper.pipeline.add_middlewares(middleware_type, name, middleware)


def register_pipeline_add(scraper: MockAIOScraper, name: str) -> None:
    scraper.pipeline.add(name, RealPipeline("add"))


def register_pipeline_decorator(scraper: MockAIOScraper, name: str) -> None:
    @scraper.pipeline(name, "decorator")
    class _(RealPipeline): ...


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "middleware_register",
    [
        pytest.param(register_via_decorator, id="middleware-decorator"),
        pytest.param(register_via_add, id="middleware-add"),
    ],
)
@pytest.mark.parametrize(
    "pipeline_register",
    [
        pytest.param(register_pipeline_add, id="pipeline-add"),
        pytest.param(register_pipeline_decorator, id="pipeline-decorator"),
    ],
)
async def test_pipeline(
    mock_aioscraper: MockAIOScraper,
    middleware_register: Callable[[MockAIOScraper, PipelineMiddlewareType, str, PipelineMiddleware[Item]]],
    pipeline_register: Callable[[MockAIOScraper, str], None],
):
    pipeline_name = "test"
    item = Item(pipeline_name)

    mock_aioscraper.server.add("https://api.test.com/v1", handler=lambda _: MockResponse(text=item.pipeline_name))

    scraper = Scraper()
    mock_aioscraper(scraper)
    async with mock_aioscraper:
        pipeline_register(mock_aioscraper, pipeline_name)
        middleware_register(mock_aioscraper, "pre", pipeline_name, pre_processing_middleware)
        middleware_register(mock_aioscraper, "post", pipeline_name, post_processing_middleware)
        await mock_aioscraper.start()

    mock_aioscraper.server.assert_all_routes_handled()

    container = mock_aioscraper.pipeline.pipelines[pipeline_name]
    pipeline = container.pipelines[0]

    assert isinstance(pipeline, RealPipeline)
    assert len(pipeline.items) == 1
    assert pipeline.items[0].pipeline_name == item.pipeline_name
    assert pipeline.items[0].from_pre
    assert pipeline.items[0].is_processed
    assert pipeline.labels in [("add",), ("decorator",)]
    assert pipeline.closed


@pytest.mark.asyncio
async def test_pipeline_dispatcher_not_found():
    mock_item = Item("test")
    dispatcher = PipelineDispatcher(PipelineConfig(), {})

    with pytest.raises(PipelineException):
        await dispatcher.put_item(mock_item)


@pytest.mark.asyncio
async def test_pipeline_dispatcher_not_strict(caplog):
    mock_item = Item("missing")
    dispatcher = PipelineDispatcher(PipelineConfig(strict=False), {})

    caplog.set_level("WARNING")
    result = await dispatcher.put_item(mock_item)

    assert result is mock_item
    assert "pipelines for item" in caplog.text


@dataclass
class CountItem:
    pipeline_name: str
    total: int = 0


class OrderPipeline(BasePipeline[CountItem]):
    def __init__(self, increment: int, audit: list[str], label: str) -> None:
        self.increment = increment
        self.audit = audit
        self.label = label
        self.closed = False

    async def put_item(self, item: CountItem) -> CountItem:
        self.audit.append(self.label)
        item.total += self.increment
        return item

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_pipeline_multiple_pipelines_order_and_close():
    audit: list[str] = []
    first = OrderPipeline(1, audit, "first")
    second = OrderPipeline(10, audit, "second")

    async def pre_one(item: CountItem) -> CountItem:
        audit.append("pre1")
        return item

    async def pre_two(item: CountItem) -> CountItem:
        audit.append("pre2")
        return item

    async def post_one(item: CountItem) -> CountItem:
        audit.append("post1")
        return item

    async def post_two(item: CountItem) -> CountItem:
        audit.append("post2")
        return item

    dispatcher = PipelineDispatcher(
        PipelineConfig(),
        {
            "count": PipelineContainer(
                pipelines=[first, second],
                pre_middlewares=[pre_one, pre_two],
                post_middlewares=[post_one, post_two],
            )
        },
    )

    result = await dispatcher.put_item(CountItem("count"))
    await dispatcher.close()

    assert result.total == 11
    assert audit == ["pre1", "pre2", "first", "second", "post1", "post2"]
    assert first.closed is True
    assert second.closed is True
