from typing import Any
import pytest

from aioscraper.types import Request, Response, SendRequest
from tests.mocks import MockAIOScraper


class Scraper:
    def __init__(self, payload: bytes):
        self.payload = payload
        self.response_data: dict[str, Any] | None = None

    async def __call__(self, send_request: SendRequest):
        await send_request(
            Request(
                url="https://api.test.com/binary",
                method="POST",
                data=self.payload,
                headers={"Content-Type": "application/octet-stream"},
                callback=self.parse,
            )
        )

    async def parse(self, response: Response):
        self.response_data = await response.json()


@pytest.mark.asyncio
async def test_binary_body_sent_as_bytes(mock_aioscraper: MockAIOScraper):
    payload = bytes(range(256)) * 4  # 1 KB of binary data
    seen_body: bytes | None = None

    async def handler(req):
        nonlocal seen_body
        seen_body = await req.read()
        return {"length": len(seen_body) if seen_body is not None else 0}

    mock_aioscraper.server.add("https://api.test.com/binary", method="POST", handler=handler)

    scraper = Scraper(payload)
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.start()

    mock_aioscraper.server.assert_all_routes_handled()

    assert seen_body == payload
    assert scraper.response_data is not None
    assert scraper.response_data["length"] == len(payload)
