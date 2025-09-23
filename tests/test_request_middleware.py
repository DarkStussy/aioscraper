import pytest
from aresponses import ResponsesMockServer

from aioscraper import AIOScraper, BaseScraper
from aioscraper.types import Request, Response, RequestParams, RequestSender


class RequestMiddleware:
    def __init__(self, mw_type: str) -> None:
        self.mw_type = mw_type

    async def __call__(self, request: Request, request_params: RequestParams) -> None:
        if request_params.cb_kwargs is not None:
            request_params.cb_kwargs[f"from_{self.mw_type}_middleware"] = True
        else:
            request_params.cb_kwargs = {f"from_{self.mw_type}_middleware": True}


class Scraper(BaseScraper):
    def __init__(self) -> None:
        self.response_data = None
        self.from_outer_middleware = None
        self.from_inner_middleware = None

    async def start(self, send_request: RequestSender) -> None:
        await send_request(url="https://api.test.com/v1", callback=self.parse)

    async def parse(self, response: Response, from_outer_middleware: str, from_inner_middleware: str) -> None:
        self.response_data = response.json()
        self.from_outer_middleware = from_outer_middleware
        self.from_inner_middleware = from_inner_middleware


@pytest.mark.asyncio
async def test_request_middleware(aresponses: ResponsesMockServer):
    response_data = {"status": "OK"}
    aresponses.add("api.test.com", "/v1", "GET", response=response_data)  # type: ignore

    scraper = Scraper()
    async with AIOScraper([scraper]) as executor:
        executor.add_outer_request_middlewares(RequestMiddleware("outer"))
        executor.add_inner_request_middlewares(RequestMiddleware("inner"))
        await executor.start()

    assert scraper.response_data == response_data
    assert scraper.from_outer_middleware is True
    assert scraper.from_inner_middleware is True
    aresponses.assert_plan_strictly_followed()
