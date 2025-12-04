import asyncio
import pytest
from aresponses import ResponsesMockServer

from aioscraper import AIOScraper
from aioscraper.config import Config, SchedulerConfig
from aioscraper.types import Request, SendRequest, Response


class PriorityScraper:
    def __init__(self) -> None:
        self.order: list[int] = []

    async def __call__(self, send_request: SendRequest) -> None:
        for priority in range(1, 4):
            await send_request(Request(url="https://api.test.com/v1", callback=self.parse, priority=priority))

    async def parse(self, response: Response, request: Request) -> None:
        self.order.append(request.priority)


@pytest.mark.asyncio
async def test_request_priority_order(aresponses: ResponsesMockServer):
    async def handle_request(request):
        await asyncio.sleep(0.1)
        return aresponses.Response(status=200, text="OK")

    aresponses.add("api.test.com", "/v1", "GET", response=handle_request, repeat=3)  # type: ignore

    scraper = PriorityScraper()
    async with AIOScraper(scraper) as s:
        await s.start(Config(scheduler=SchedulerConfig(concurrent_requests=1, pending_requests=3)))

    assert scraper.order == [1, 2, 3]
    aresponses.assert_plan_strictly_followed()
