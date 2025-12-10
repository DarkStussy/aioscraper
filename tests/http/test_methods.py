import pytest

from aioscraper.types import Request, Response, SendRequest
from tests.mocks import MockAIOScraper


class Scraper:
    def __init__(self):
        self.results: dict[str, dict] = {}

    async def __call__(self, send_request: SendRequest):
        await send_request(
            Request(
                url="https://api.test.com/get",
                method="GET",
                callback=self.parse,
                cb_kwargs={"expect": "GET"},
            ),
        )
        await send_request(
            Request(
                url="https://api.test.com/post",
                method="POST",
                json_data={"foo": "bar"},
                callback=self.parse,
                cb_kwargs={"expect": "POST"},
            ),
        )
        await send_request(
            Request(
                url="https://api.test.com/put",
                method="PUT",
                data="payload",
                callback=self.parse,
                cb_kwargs={"expect": "PUT"},
            ),
        )
        await send_request(
            Request(
                url="https://api.test.com/delete",
                method="DELETE",
                callback=self.parse,
                cb_kwargs={"expect": "DELETE"},
            ),
        )
        await send_request(
            Request(
                url="https://api.test.com/patch",
                method="PATCH",
                json_data={"patch": True},
                callback=self.parse,
                cb_kwargs={"expect": "PATCH"},
            ),
        )

    async def parse(self, response: Response, request: Request, expect: str):
        self.results[expect] = await response.json()


@pytest.mark.asyncio
async def test_http_methods(mock_aioscraper: MockAIOScraper):
    async def handle_post(req):
        body = await req.json()
        return {"method": req.method, "body": body}

    async def handle_put(req):
        body = await req.text()
        return {"method": req.method, "body": body}

    async def handle_patch(req):
        body = await req.json()
        return {"method": req.method, "body": body}

    mock_aioscraper.server.add("https://api.test.com/get", method="GET", handler=lambda _: {"method": "GET"})
    mock_aioscraper.server.add("https://api.test.com/post", method="POST", handler=handle_post)
    mock_aioscraper.server.add("https://api.test.com/put", method="PUT", handler=handle_put)
    mock_aioscraper.server.add("https://api.test.com/delete", method="DELETE", handler=lambda _: {"method": "DELETE"})
    mock_aioscraper.server.add("https://api.test.com/patch", method="PATCH", handler=handle_patch)

    scraper = Scraper()
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.wait()

    mock_aioscraper.server.assert_all_routes_handled()

    assert scraper.results == {
        "GET": {"method": "GET"},
        "POST": {"method": "POST", "body": {"foo": "bar"}},
        "PUT": {"method": "PUT", "body": "payload"},
        "DELETE": {"method": "DELETE"},
        "PATCH": {"method": "PATCH", "body": {"patch": True}},
    }
