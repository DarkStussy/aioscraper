import pytest

from aioscraper.types import Request, Response, SendRequest, File
from tests.mocks import MockAIOScraper


class Scraper:
    def __init__(self):
        self.result: dict | None = None

    async def __call__(self, send_request: SendRequest):
        await send_request(
            Request(
                url="https://api.test.com/form",
                method="POST",
                data={"field": "value", "number": "123"},
                files={"file": File("hello.txt", b"hello", "text/plain")},
                callback=self.parse,
            )
        )

    async def parse(self, response: Response, request: Request):
        self.result = response.json()


@pytest.mark.asyncio
async def test_form_and_file_upload(mock_aioscraper: MockAIOScraper):
    async def handler(req):
        data: dict[str, str] = {}
        if req.content_type.startswith("multipart/"):
            reader = await req.multipart()
            async for part in reader:
                if part.filename:
                    data[part.name] = (await part.read(decode=False)).decode()
                else:
                    data[part.name] = await part.text()
        else:
            data = {k: v for k, v in (await req.post()).items()}

        return {"content_type": req.content_type, "data": data}

    mock_aioscraper.server.add("https://api.test.com/form", method="POST", handler=handler)

    scraper = Scraper()
    mock_aioscraper(scraper)

    async with mock_aioscraper:
        await mock_aioscraper.start()

    mock_aioscraper.server.assert_all_routes_handled()

    assert scraper.result is not None
    assert scraper.result["content_type"].startswith("multipart/")
    assert scraper.result["data"] == {"field": "value", "number": "123", "file": "hello"}
