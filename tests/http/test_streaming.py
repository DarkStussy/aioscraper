import asyncio

import pytest
from aiohttp import web

from aioscraper.types import Request, Response, SendRequest
from tests.mocks import MockAIOScraper, MockResponse


class Scraper:
    def __init__(self) -> None:
        self.bodies: dict[str, bytes] = {}

    async def __call__(self, send_request: SendRequest) -> None:
        await send_request(
            Request(
                url="https://api.test.com/chunked",
                method="GET",
                callback=self.store_body,
                cb_kwargs={"key": "chunked"},
            )
        )
        await send_request(
            Request(
                url="https://api.test.com/large",
                method="GET",
                callback=self.store_body,
                cb_kwargs={"key": "large"},
            )
        )

    async def store_body(self, response: Response, key: str) -> None:
        self.bodies[key] = response.content


@pytest.mark.asyncio
async def test_streamed_and_chunked_bodies_are_fully_read(mock_aioscraper: MockAIOScraper):
    chunks = [b"A" * 65536, b"B" * 32768, b"end"]

    async def chunked_handler(req):
        resp = web.StreamResponse(status=200, headers={"Content-Type": "application/octet-stream"})
        await resp.prepare(req)

        for chunk in chunks:
            await resp.write(chunk)
            await asyncio.sleep(0)  # simulate streamed chunks arriving over time

        await resp.write_eof()
        return resp

    large_text = "0123456789abcdef" * 16384  # ~256 KB

    mock_aioscraper.server.add("https://api.test.com/chunked", handler=chunked_handler)
    mock_aioscraper.server.add("https://api.test.com/large", handler=lambda _: MockResponse(text=large_text))

    scraper = Scraper()
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.start()

    mock_aioscraper.server.assert_all_routes_handled()

    assert scraper.bodies["chunked"] == b"".join(chunks)
    assert scraper.bodies["large"] == large_text.encode()
