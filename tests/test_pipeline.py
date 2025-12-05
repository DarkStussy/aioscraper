import pytest
from dataclasses import dataclass

from aioscraper.config import PipelineConfig
from aioscraper.exceptions import PipelineException
from aioscraper.types import Pipeline, Request, SendRequest, Response
from aioscraper.pipeline import BasePipeline
from aioscraper.pipeline.dispatcher import PipelineContainer, PipelineDispatcher

from .mocks import MockAIOScraper, MockResponse


@dataclass
class Item:
    pipeline_name: str
    is_processed: bool = False


class RealPipeline(BasePipeline[Item]):
    def __init__(self) -> None:
        self.items: list[Item] = []
        self.closed = False

    async def put_item(self, item: Item) -> Item:
        self.items.append(item)
        return item

    async def close(self) -> None:
        self.closed = True


async def pre_processing_middleware(item: Item) -> Item:
    assert item.pipeline_name == "test"
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


@pytest.mark.asyncio
async def test_pipeline(mock_aioscraper: MockAIOScraper):
    item = Item("test")
    pipeline = RealPipeline()

    mock_aioscraper.server.add("https://api.test.com/v1", handler=lambda _: MockResponse(text=item.pipeline_name))

    scraper = Scraper()
    mock_aioscraper.register(scraper)
    async with mock_aioscraper:
        mock_aioscraper.add_pipelines(item.pipeline_name, pipeline)
        mock_aioscraper.add_pipeline_pre_middlewares(item.pipeline_name, pre_processing_middleware)
        mock_aioscraper.add_pipeline_post_middlewares(item.pipeline_name, post_processing_middleware)
        await mock_aioscraper.start()

    mock_aioscraper.server.assert_all_routes_handled()

    assert len(pipeline.items) == 1
    assert pipeline.items[0].pipeline_name == item.pipeline_name
    assert pipeline.items[0].is_processed
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
