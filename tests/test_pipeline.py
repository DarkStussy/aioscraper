import pytest
from dataclasses import dataclass
from aresponses import ResponsesMockServer

from aioscraper import AIOScraper
from aioscraper.config import PipelineConfig
from aioscraper.exceptions import PipelineException
from aioscraper.types import Pipeline, Request, SendRequest, Response
from aioscraper.pipeline import BasePipeline
from aioscraper.pipeline.dispatcher import PipelineDispatcher


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
async def test_pipeline(aresponses: ResponsesMockServer):
    item = Item("test")
    pipeline = RealPipeline()

    aresponses.add("api.test.com", "/v1", "GET", response=item.pipeline_name)  # type: ignore

    async with AIOScraper(Scraper()) as s:
        s.add_pipelines(item.pipeline_name, pipeline)
        s.add_pipeline_pre_middlewares(item.pipeline_name, pre_processing_middleware)
        s.add_pipeline_post_middlewares(item.pipeline_name, post_processing_middleware)
        await s.start()

    aresponses.assert_plan_strictly_followed()

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
