import pytest
from aresponses import ResponsesMockServer

from aioscraper import AIOScraper, BaseScraper
from aioscraper.exceptions import ClientException, HTTPException
from aioscraper.types import RequestSender


class Scraper(BaseScraper):
    def __init__(self) -> None:
        self.status = None
        self.response_data = None

    async def start(self, send_request: RequestSender) -> None:
        await send_request(url="https://api.test.com/v1", errback=self.errback)

    async def errback(self, exc: ClientException) -> None:
        if isinstance(exc, HTTPException):
            self.status = exc.status_code
            self.response_data = exc.message


@pytest.mark.asyncio
async def test_error(aresponses: ResponsesMockServer):
    response_data = "Internal Server Error"

    def handle_request(request):
        return aresponses.Response(status=500, text=response_data)

    aresponses.add("api.test.com", "/v1", "GET", response=handle_request)  # pyright: ignore

    scraper = Scraper()
    async with AIOScraper([scraper]) as executor:
        await executor.start()

    assert scraper.status == 500
    assert scraper.response_data == response_data
    aresponses.assert_plan_strictly_followed()
