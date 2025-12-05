import asyncio
import pytest

from aioscraper.config import Config, SchedulerConfig
from aioscraper.types import Request, SendRequest, Response
from tests.mocks.scraper import MockAIOScraper
from tests.mocks.server import MockResponse


class PriorityScraper:
    def __init__(self) -> None:
        self.order: list[int] = []

    async def __call__(self, send_request: SendRequest) -> None:
        for priority in range(1, 4):
            await send_request(Request(url="https://api.test.com/v1", callback=self.parse, priority=priority))

    async def parse(self, response: Response, request: Request) -> None:
        self.order.append(request.priority)


@pytest.mark.asyncio
async def test_request_priority_order(mock_aioscraper: MockAIOScraper):
    async def handle_request(_) -> MockResponse:
        await asyncio.sleep(0.1)
        return MockResponse(text="OK")

    mock_aioscraper.server.add("https://api.test.com/v1", handler=handle_request, repeat=3)

    scraper = PriorityScraper()
    mock_aioscraper.register(scraper)
    async with mock_aioscraper:
        await mock_aioscraper.start(Config(scheduler=SchedulerConfig(concurrent_requests=1, pending_requests=3)))

    assert scraper.order == [1, 2, 3]
    mock_aioscraper.server.assert_all_routes_handled()
