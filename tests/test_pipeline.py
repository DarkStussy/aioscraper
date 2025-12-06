from typing import Callable
from dataclasses import dataclass

import pytest

from aioscraper.config import PipelineConfig
from aioscraper.exceptions import PipelineException, StopMiddlewareProcessing, StopItemProcessing
from aioscraper.types.session import Request, SendRequest, Response
from aioscraper.types.pipeline import Pipeline, PipelineMiddleware, PipelineMiddlewareStage
from aioscraper.scraper.pipeline import PipelineContainer, PipelineDispatcher
from tests.mocks import MockAIOScraper, MockResponse


@dataclass
class RealItem:
    value: str
    is_processed: bool = False
    from_pre: bool = False


class RealPipeline:
    def __init__(self, *labels: str) -> None:
        self.items: list[RealItem] = []
        self.closed = False
        self.labels = labels

    async def put_item(self, item: RealItem) -> RealItem:
        self.items.append(item)
        return item

    async def close(self) -> None:
        self.closed = True


async def pre_processing_middleware(item: RealItem) -> RealItem:
    assert isinstance(item, RealItem)
    item.from_pre = True
    return item


async def post_processing_middleware(item: RealItem) -> RealItem:
    assert isinstance(item, RealItem)
    item.is_processed = True
    return item


class Scraper:
    async def __call__(self, send_request: SendRequest) -> None:
        await send_request(Request(url="https://api.test.com/v1", callback=self.parse))

    async def parse(self, response: Response, pipeline: Pipeline) -> None:
        await pipeline(RealItem(response.text()))


def _add_via_decorator(
    scraper: MockAIOScraper, stage: PipelineMiddlewareStage, middleware: PipelineMiddleware[RealItem]
):
    scraper.pipeline.middleware(stage, RealItem)(middleware)


def _add(scraper: MockAIOScraper, stage: PipelineMiddlewareStage, middleware: PipelineMiddleware[RealItem]):
    scraper.pipeline.add_middlewares(stage, RealItem, middleware)


def _add_pipeline(scraper: MockAIOScraper) -> None:
    scraper.pipeline.add(RealItem, RealPipeline("add"))


def _add_pipeline_via_decorator(scraper: MockAIOScraper):
    @scraper.pipeline(RealItem, "decorator")
    class _(RealPipeline): ...


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "add_middleware",
    [
        pytest.param(_add_via_decorator, id="middleware-decorator"),
        pytest.param(_add, id="middleware-add"),
    ],
)
@pytest.mark.parametrize(
    "add_pipeline",
    [
        pytest.param(_add_pipeline, id="pipeline-add"),
        pytest.param(_add_pipeline_via_decorator, id="pipeline-decorator"),
    ],
)
async def test_pipeline(
    mock_aioscraper: MockAIOScraper,
    add_middleware: Callable[[MockAIOScraper, PipelineMiddlewareStage, PipelineMiddleware[RealItem]], None],
    add_pipeline: Callable[[MockAIOScraper], None],
):

    mock_aioscraper.server.add("https://api.test.com/v1", handler=lambda _: MockResponse(text="test"))

    scraper = Scraper()
    mock_aioscraper(scraper)
    async with mock_aioscraper:
        add_pipeline(mock_aioscraper)
        add_middleware(mock_aioscraper, "pre", pre_processing_middleware)
        add_middleware(mock_aioscraper, "post", post_processing_middleware)
        await mock_aioscraper.start()

    mock_aioscraper.server.assert_all_routes_handled()

    container = mock_aioscraper.pipeline.pipelines[RealItem]
    pipeline = container.pipelines[0]

    assert isinstance(pipeline, RealPipeline)
    assert len(pipeline.items) == 1
    assert pipeline.items[0].from_pre
    assert pipeline.items[0].is_processed
    assert pipeline.labels in [("add",), ("decorator",)]
    assert pipeline.closed


@pytest.mark.asyncio
async def test_pipeline_dispatcher_not_found():
    mock_item = RealItem("test")
    dispatcher = PipelineDispatcher(PipelineConfig(), {})

    with pytest.raises(PipelineException):
        await dispatcher.put_item(mock_item)


@pytest.mark.asyncio
async def test_pipeline_dispatcher_not_strict(caplog):
    mock_item = RealItem("missing")
    dispatcher = PipelineDispatcher(PipelineConfig(strict=False), {})

    caplog.set_level("WARNING")
    result = await dispatcher.put_item(mock_item)

    assert result is mock_item
    assert "pipelines for item" in caplog.text


@dataclass
class CountItem:
    total: int = 0


class OrderPipeline:
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
            CountItem: PipelineContainer(
                pipelines=[first, second],
                pre_middlewares=[pre_one, pre_two],
                post_middlewares=[post_one, post_two],
            )
        },
    )

    result = await dispatcher.put_item(CountItem())
    await dispatcher.close()

    assert result.total == 11
    assert audit == ["pre1", "pre2", "first", "second", "post1", "post2"]
    assert first.closed is True
    assert second.closed is True


class AuditPipeline:
    def __init__(self) -> None:
        self.audit = []
        self.closed = False

    async def put_item(self, item: CountItem) -> CountItem:
        self.audit.append("pipeline")
        item.total += 1
        return item

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_pipeline_pre_middleware_stop_processing_skips_rest_and_pipelines():
    pipeline = AuditPipeline()

    async def pre_one(item: CountItem) -> CountItem:
        raise StopMiddlewareProcessing

    async def pre_two(item: CountItem) -> CountItem:
        pipeline.audit.append("pre2")
        return item

    async def post_one(item: CountItem) -> CountItem:
        pipeline.audit.append("post")
        return item

    dispatcher = PipelineDispatcher(
        PipelineConfig(),
        {
            CountItem: PipelineContainer(
                pipelines=[pipeline],
                pre_middlewares=[pre_one, pre_two],
                post_middlewares=[post_one],
            )
        },
    )

    result = await dispatcher.put_item(CountItem())
    await dispatcher.close()

    assert pipeline.closed is True
    assert result.total == 1
    assert pipeline.audit == ["pipeline", "post"]  # pre2 skipped, pipeline and post executed


@pytest.mark.asyncio
async def test_pipeline_pre_stop_item_processing_returns_early():
    pipeline = AuditPipeline()

    async def pre_stop(item: CountItem) -> CountItem:
        raise StopItemProcessing

    async def post_one(item: CountItem) -> CountItem:
        pipeline.audit.append("post")
        return item

    dispatcher = PipelineDispatcher(
        PipelineConfig(),
        {
            CountItem: PipelineContainer(
                pipelines=[pipeline],
                pre_middlewares=[pre_stop],
                post_middlewares=[post_one],
            )
        },
    )

    result = await dispatcher.put_item(CountItem())
    await dispatcher.close()

    assert pipeline.closed is True
    assert result.total == 0
    assert pipeline.audit == []


@pytest.mark.asyncio
async def test_pipeline_post_stop_processing_skips_remaining_posts():
    pipeline = AuditPipeline()

    async def post_one(item: CountItem) -> CountItem:
        raise StopMiddlewareProcessing

    async def post_two(item: CountItem) -> CountItem:
        pipeline.audit.append("post2")
        return item

    dispatcher = PipelineDispatcher(
        PipelineConfig(),
        {
            CountItem: PipelineContainer(
                pipelines=[pipeline],
                pre_middlewares=[],
                post_middlewares=[post_one, post_two],
            )
        },
    )

    result = await dispatcher.put_item(CountItem())
    await dispatcher.close()

    assert pipeline.closed is True
    assert result.total == 1
    assert pipeline.audit == ["pipeline"]
