from contextlib import asynccontextmanager

from aioscraper import AIOScraper
from aioscraper.types import Request, Response, SendRequest


async def scrape(send_request: SendRequest):
    await send_request(Request(url="https://example.com", callback=handle_response))


async def handle_response(response: Response):
    print(f"Fetched {response.url} with status {response.status}")


@asynccontextmanager
async def lifespan(scraper: AIOScraper):
    scraper.register(scrape)
    yield
    # cleanup some resources...
