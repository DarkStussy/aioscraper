import pytest

from aioscraper.types import Request, Response, SendRequest
from tests.mocks.scraper import MockAIOScraper


class RequestMiddleware:
    def __init__(self, mw_type: str) -> None:
        self.mw_type = mw_type

    async def __call__(self, request: Request) -> None:
        request.state[f"from_{self.mw_type}_middleware"] = True
        request.cb_kwargs[f"from_{self.mw_type}_middleware"] = True


class Scraper:
    def __init__(self) -> None:
        self.response_data = None
        self.from_outer_middleware = None
        self.from_inner_middleware = None
        self.state: dict[str, bool] | None = None

    async def __call__(self, send_request: SendRequest) -> None:
        await send_request(Request(url="https://api.test.com/v1", callback=self.parse))

    async def parse(
        self,
        response: Response,
        request: Request,
        from_outer_middleware: str,
        from_inner_middleware: str,
    ) -> None:
        self.response_data = response.json()
        self.from_outer_middleware = from_outer_middleware
        self.from_inner_middleware = from_inner_middleware
        self.state = dict(request.state)


@pytest.mark.asyncio
async def test_request_middleware(mock_aioscraper: MockAIOScraper):
    response_data = {"status": "OK"}
    mock_aioscraper.server.add("https://api.test.com/v1", handler=lambda _: response_data)

    scraper = Scraper()
    mock_aioscraper(scraper)
    async with mock_aioscraper:
        mock_aioscraper.add_outer_request_middlewares(RequestMiddleware("outer"))
        mock_aioscraper.add_inner_request_middlewares(RequestMiddleware("inner"))
        await mock_aioscraper.start()

    assert scraper.response_data == response_data
    assert scraper.from_outer_middleware is True
    assert scraper.from_inner_middleware is True
    assert scraper.state == {"from_outer_middleware": True, "from_inner_middleware": True}
    mock_aioscraper.server.assert_all_routes_handled()
