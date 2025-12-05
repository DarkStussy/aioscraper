import pytest

from aioscraper.types import Request, SendRequest, Response
from tests.mocks.scraper import MockAIOScraper


class ResponseMiddleware:
    def __init__(self) -> None:
        self.response_data = None
        self.mv_param = None

    async def __call__(self, response: Response, request: Request) -> None:
        self.response_data = response.json()
        self.mv_param = request.cb_kwargs["mv_param"]
        request.state["from_response_middleware"] = True


class Scraper:
    def __init__(self) -> None:
        self.response_data = None
        self.from_response_middleware = None

    async def __call__(self, send_request: SendRequest) -> None:
        await send_request(Request(url="https://api.test.com/v1", callback=self.parse, cb_kwargs={"mv_param": True}))

    async def parse(self, response: Response, request: Request) -> None:
        self.response_data = response.json()
        self.from_response_middleware = request.state["from_response_middleware"]


@pytest.mark.asyncio
async def test_response_middleware(mock_aioscraper: MockAIOScraper):
    response_data = {"status": "OK"}
    mock_aioscraper.server.add("https://api.test.com/v1", handler=lambda _: response_data)

    middleware = ResponseMiddleware()
    scraper = Scraper()
    mock_aioscraper(scraper)
    async with mock_aioscraper:
        mock_aioscraper.add_response_middlewares(middleware)
        await mock_aioscraper.start()

    assert scraper.response_data == response_data
    assert middleware.response_data == response_data
    assert middleware.mv_param is True
    assert scraper.from_response_middleware is True
    mock_aioscraper.server.assert_all_routes_handled()
