import pytest
from aresponses import ResponsesMockServer

from aioscraper import AIOScraper
from aioscraper.types import Request, SendRequest, Response


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
async def test_response_middleware(aresponses: ResponsesMockServer):
    response_data = {"status": "OK"}
    aresponses.add("api.test.com", "/v1", "GET", response=response_data)  # type: ignore

    middleware = ResponseMiddleware()
    scraper = Scraper()
    async with AIOScraper(scraper) as s:
        s.add_response_middlewares(middleware)
        await s.start()

    assert scraper.response_data == response_data
    assert middleware.response_data == response_data
    assert middleware.mv_param is True
    assert scraper.from_response_middleware is True
    aresponses.assert_plan_strictly_followed()
