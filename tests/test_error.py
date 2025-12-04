import pytest
from aresponses import ResponsesMockServer

from aioscraper import AIOScraper
from aioscraper.exceptions import ClientException, HTTPException
from aioscraper.types import Request, SendRequest, Response


class Scraper:
    def __init__(self) -> None:
        self.status = None
        self.response_data = None

    async def __call__(self, send_request: SendRequest) -> None:
        await send_request(Request(url="https://api.test.com/v1", errback=self.errback))

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
    async with AIOScraper(scraper) as s:
        await s.start()

    assert scraper.status == 500
    assert scraper.response_data == response_data
    aresponses.assert_plan_strictly_followed()


class CallbackErrorScraper:
    def __init__(self) -> None:
        self.exc_message = None
        self.request_url = None

    async def __call__(self, send_request: SendRequest) -> None:
        await send_request(Request(url="https://api.test.com/v2", callback=self.parse, errback=self.errback))

    async def parse(self, response: Response) -> None:
        raise RuntimeError("parse failed")

    async def errback(self, exc: Exception, request: Request) -> None:
        self.exc_message = str(exc)
        self.request_url = request.url


@pytest.mark.asyncio
async def test_callback_error_triggers_errback(aresponses: ResponsesMockServer):
    aresponses.add("api.test.com", "/v2", "GET", response={"status": "OK"})  # type: ignore

    scraper = CallbackErrorScraper()
    async with AIOScraper(scraper) as s:
        await s.start()

    assert scraper.exc_message == "parse failed"
    assert scraper.request_url == "https://api.test.com/v2"
    aresponses.assert_plan_strictly_followed()


class ErrbackKwargsScraper:
    def __init__(self) -> None:
        self.status = None
        self.meta = None

    async def __call__(self, send_request: SendRequest) -> None:
        await send_request(Request(url="https://api.test.com/v3", errback=self.errback, cb_kwargs={"meta": "value"}))

    async def errback(self, exc: ClientException, meta: str) -> None:
        if isinstance(exc, HTTPException):
            self.status = exc.status_code
        self.meta = meta


@pytest.mark.asyncio
async def test_errback_receives_cb_kwargs(aresponses: ResponsesMockServer):
    def handle_request(request):
        return aresponses.Response(status=503, text="Service Unavailable")

    aresponses.add("api.test.com", "/v3", "GET", response=handle_request)  # type: ignore

    scraper = ErrbackKwargsScraper()
    async with AIOScraper(scraper) as s:
        await s.start()

    assert scraper.status == 503
    assert scraper.meta == "value"
    aresponses.assert_plan_strictly_followed()
