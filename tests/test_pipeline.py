from dataclasses import dataclass, field
from typing import Any, Callable

import pytest

from aioscraper.config import PipelineConfig
from aioscraper.core.pipeline import PipelineDispatcher
from aioscraper.exceptions import PipelineException, StopItemProcessing, StopMiddlewareProcessing
from aioscraper.types.pipeline import (
    GlobalPipelineMiddleware,
    ItemHandler,
    Pipeline,
    PipelineContainer,
    PipelineMiddleware,
    PipelineMiddlewareStage,
)
from aioscraper.types.session import Request, Response, SendRequest
from tests.mocks import MockAIOScraper, MockResponse


@dataclass
class RealItem:
    value: str
    is_processed: bool = False
    from_pre: bool = False
    history: list[str] = field(default_factory=list)


class RealPipeline:
    def __init__(self, *labels: str):
        self.items: list[RealItem] = []
        self.closed = False
        self.labels = labels

    async def put_item(self, item: RealItem) -> RealItem:
        item.history.append(f"pipeline-{self.labels[0]}")
        self.items.append(item)
        return item

    async def close(self):
        self.closed = True


async def pre_processing_middleware(item: RealItem) -> RealItem:
    assert isinstance(item, RealItem)
    item.from_pre = True
    item.history.append("pre")
    return item


async def post_processing_middleware(item: RealItem) -> RealItem:
    assert isinstance(item, RealItem)
    item.is_processed = True
    item.history.append("post")
    return item


class Scraper:
    async def __call__(self, send_request: SendRequest):
        await send_request(Request(url="https://api.test.com/v1", callback=self.parse))

    async def parse(self, response: Response, pipeline: Pipeline):
        await pipeline(RealItem(await response.text()))


def _add_via_decorator(
    scraper: MockAIOScraper,
    stage: PipelineMiddlewareStage,
    middleware: PipelineMiddleware[RealItem],
):
    scraper.pipeline.middleware(stage, RealItem)(middleware)


def _add(scraper: MockAIOScraper, stage: PipelineMiddlewareStage, middleware: PipelineMiddleware[RealItem]):
    scraper.pipeline.add_middlewares(stage, RealItem, middleware)


def _add_pipeline(scraper: MockAIOScraper):
    scraper.pipeline.add(RealItem, RealPipeline("add"))


def _add_pipeline_via_decorator(scraper: MockAIOScraper):
    @scraper.pipeline(RealItem, "decorator")
    class _TestPipeline(RealPipeline): ...


def global_middleware_factory(global_label: str) -> GlobalPipelineMiddleware[RealItem]:
    async def middleware(handler: Pipeline[RealItem], item: RealItem) -> RealItem:
        item.history.append(f"{global_label}-before")
        item = await handler(item)
        item.history.append(f"{global_label}-after")
        return item

    return middleware


def _add_global_middleware(
    scraper: MockAIOScraper,
    middleware: Callable[[str], GlobalPipelineMiddleware[RealItem]],
):
    scraper.pipeline.add_global_middlewares(middleware)


def _add_global_middleware_via_decorator(
    scraper: MockAIOScraper,
    middleware: Callable[[str], GlobalPipelineMiddleware[RealItem]],
):
    @scraper.pipeline.global_middleware
    def _(global_label: str) -> GlobalPipelineMiddleware[RealItem]:
        return middleware(global_label)


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
@pytest.mark.parametrize(
    "add_global_middleware",
    [
        pytest.param(_add_global_middleware, id="global-middleware-add"),
        pytest.param(_add_global_middleware_via_decorator, id="global-middleware-decorator"),
    ],
)
async def test_pipeline(
    mock_aioscraper: MockAIOScraper,
    add_middleware: Callable[[MockAIOScraper, PipelineMiddlewareStage, PipelineMiddleware[RealItem]], None],
    add_pipeline: Callable[[MockAIOScraper], None],
    add_global_middleware: Callable[[MockAIOScraper, Callable[[str], GlobalPipelineMiddleware[RealItem]]], None],
):
    mock_aioscraper.server.add("https://api.test.com/v1", handler=lambda _: MockResponse(text="test"))

    scraper = Scraper()
    mock_aioscraper(scraper)
    global_label = "global"
    mock_aioscraper.add_dependencies(global_label=global_label)
    async with mock_aioscraper:
        add_pipeline(mock_aioscraper)
        add_middleware(mock_aioscraper, "pre", pre_processing_middleware)
        add_middleware(mock_aioscraper, "post", post_processing_middleware)
        add_global_middleware(mock_aioscraper, global_middleware_factory)
        await mock_aioscraper.wait()

    mock_aioscraper.server.assert_all_routes_handled()

    container = mock_aioscraper.pipeline.pipelines[RealItem]
    pipeline = container.pipelines[0]

    assert isinstance(pipeline, RealPipeline)
    assert len(pipeline.items) == 1
    item = pipeline.items[0]
    assert item.from_pre
    assert item.is_processed
    assert pipeline.labels in [("add",), ("decorator",)]
    assert pipeline.closed
    assert item.history == [
        f"{global_label}-before",
        "pre",
        f"pipeline-{pipeline.labels[0]}",
        "post",
        f"{global_label}-after",
    ]


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
    assert "Pipeline not found for item type" in caplog.text


@dataclass
class StateItem:
    total: int = 0
    state: str | None = None
    history: list[str] = field(default_factory=list)


class OrderPipeline:
    def __init__(self, increment: int, label: str):
        self.increment = increment
        self.label = label
        self.closed = False

    async def put_item(self, item: StateItem) -> StateItem:
        item.history.append(self.label)
        item.total += self.increment
        return item

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_pipeline_multiple_pipelines_order_and_close():
    first = OrderPipeline(1, "first")
    second = OrderPipeline(10, "second")

    async def pre_one(item: StateItem) -> StateItem:
        item.history.append("pre1")
        return item

    async def pre_two(item: StateItem) -> StateItem:
        item.history.append("pre2")
        return item

    async def post_one(item: StateItem) -> StateItem:
        item.history.append("post1")
        return item

    async def post_two(item: StateItem) -> StateItem:
        item.history.append("post2")
        return item

    dispatcher = PipelineDispatcher(
        PipelineConfig(),
        {
            StateItem: PipelineContainer(
                pipelines=[first, second],
                pre_middlewares=[pre_one, pre_two],
                post_middlewares=[post_one, post_two],
            ),
        },
    )

    item = await dispatcher.put_item(StateItem())
    await dispatcher.close()

    assert item.total == 11
    assert item.history == ["pre1", "pre2", "first", "second", "post1", "post2"]
    assert first.closed is True
    assert second.closed is True


class AuditPipeline:
    def __init__(self):
        self.closed = False

    async def put_item(self, item: StateItem) -> StateItem:
        item.history.append("pipeline")
        item.state = "processed"
        item.total += 1
        return item

    async def close(self):
        self.closed = True


@pytest.mark.asyncio
async def test_pipeline_global_middlewares_wrap_chain_order_matches_example():
    pipeline = AuditPipeline()

    async def mw_a(handler: ItemHandler[StateItem], item: StateItem) -> StateItem:
        item.history.append("a-before")
        item = await handler(item)
        item.history.append("a-after")
        return item

    async def mw_b(handler: ItemHandler[StateItem], item: StateItem) -> StateItem:
        item.history.append("b-before")
        item = await handler(item)
        item.history.append("b-after")
        return item

    dispatcher = PipelineDispatcher(
        PipelineConfig(),
        {StateItem: PipelineContainer(pipelines=[pipeline])},
        global_middlewares=[lambda: mw_a, lambda: mw_b],
    )

    item = await dispatcher.put_item(StateItem())
    await dispatcher.close()

    assert pipeline.closed is True
    assert item.state == "processed"
    assert item.history == ["b-before", "a-before", "pipeline", "a-after", "b-after"]


@pytest.mark.asyncio
async def test_pipeline_pre_middleware_stop_processing_skips_rest_and_pipelines():
    pipeline = AuditPipeline()

    async def pre_one(item: StateItem) -> StateItem:
        raise StopMiddlewareProcessing

    async def pre_two(item: StateItem) -> StateItem:
        item.history.append("pre2")
        return item

    async def post_one(item: StateItem) -> StateItem:
        item.history.append("post")
        return item

    dispatcher = PipelineDispatcher(
        PipelineConfig(),
        {
            StateItem: PipelineContainer(
                pipelines=[pipeline],
                pre_middlewares=[pre_one, pre_two],
                post_middlewares=[post_one],
            ),
        },
    )

    item = await dispatcher.put_item(StateItem())
    await dispatcher.close()

    assert pipeline.closed is True
    assert item.total == 1
    assert item.history == ["pipeline", "post"]  # pre2 skipped, pipeline and post executed


@pytest.mark.asyncio
async def test_pipeline_pre_stop_item_processing_returns_early():
    pipeline = AuditPipeline()

    async def pre_stop(item: StateItem) -> StateItem:
        raise StopItemProcessing

    async def post_one(item: StateItem) -> StateItem:
        item.history.append("post")
        return item

    dispatcher = PipelineDispatcher(
        PipelineConfig(),
        {
            StateItem: PipelineContainer(
                pipelines=[pipeline],
                pre_middlewares=[pre_stop],
                post_middlewares=[post_one],
            ),
        },
    )

    item = await dispatcher.put_item(StateItem())
    await dispatcher.close()

    assert pipeline.closed is True
    assert item.total == 0
    assert item.history == []


@pytest.mark.asyncio
async def test_pipeline_post_stop_processing_skips_remaining_posts():
    pipeline = AuditPipeline()

    async def post_one(item: StateItem) -> StateItem:
        raise StopMiddlewareProcessing

    async def post_two(item: StateItem) -> StateItem:
        item.history.append("post2")
        return item

    dispatcher = PipelineDispatcher(
        PipelineConfig(),
        {
            StateItem: PipelineContainer(
                pipelines=[pipeline],
                pre_middlewares=[],
                post_middlewares=[post_one, post_two],
            ),
        },
    )

    item = await dispatcher.put_item(StateItem())
    await dispatcher.close()

    assert pipeline.closed is True
    assert item.total == 1
    assert item.history == ["pipeline"]


@pytest.mark.asyncio
async def test_pipeline_global_middleware_stop_item_processing_returns_item():
    pipeline = AuditPipeline()

    async def stop_item(handler: ItemHandler, item: Any):
        raise StopItemProcessing

    dispatcher = PipelineDispatcher(
        PipelineConfig(),
        {StateItem: PipelineContainer(pipelines=[pipeline])},
        global_middlewares=[lambda: stop_item],
    )

    item = await dispatcher.put_item(StateItem())
    await dispatcher.close()

    assert item.total == 0
    assert len(item.history) == 0
