import pytest
from dataclasses import dataclass
from unittest.mock import MagicMock
from aresponses import ResponsesMockServer

from aioscraper import AIOScraper, BaseScraper
from aioscraper.exceptions import PipelineException
from aioscraper.types import Pipeline, RequestSender, Response
from aioscraper.pipeline import BasePipeline
from aioscraper.pipeline.dispatcher import PipelineDispatcher


@dataclass
class Item:
    pipeline_name: str


class RealPipeline(BasePipeline[Item]):
    def __init__(self) -> None:
        self.items: list[Item] = []
        self.closed = False

    async def put_item(self, item: Item) -> None:
        self.items.append(item)

    async def close(self) -> None:
        self.closed = True


class Scraper(BaseScraper):
    async def start(self, send_request: RequestSender) -> None:
        await send_request(url="https://api.test.com/v1", callback=self.parse)

    async def parse(self, response: Response, pipeline: Pipeline) -> None:
        await pipeline(Item(response.text()))


@pytest.mark.asyncio
async def test_pipeline(aresponses: ResponsesMockServer):
    item = Item("test")
    pipeline = RealPipeline()

    aresponses.add("api.test.com", "/v1", "GET", response=item.pipeline_name)  # type: ignore

    async with AIOScraper([Scraper()]) as executor:
        executor.add_pipeline(item.pipeline_name, pipeline)
        await executor.start()

    aresponses.assert_plan_strictly_followed()

    assert len(pipeline.items) == 1
    assert pipeline.items[0].pipeline_name == item.pipeline_name
    assert pipeline.closed


@pytest.mark.asyncio
async def test_pipeline_dispatcher_not_found():
    mock_item = Item("test")
    dispatcher = PipelineDispatcher(MagicMock(), {})

    with pytest.raises(PipelineException):
        await dispatcher.put_item(mock_item)
