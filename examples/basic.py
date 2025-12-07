#!/usr/bin/env python3
"""
Minimal scraper example: fetch example.com, extract the <title>, and print it via a pipeline.

Run with the CLI:

    $ aioscraper basic
"""

import re
from dataclasses import dataclass

from aioscraper import AIOScraper
from aioscraper.types import Pipeline, Request, Response, SendRequest


scraper = AIOScraper()


@dataclass(slots=True)
class Page:
    url: str
    title: str


@scraper.pipeline(Page)
class PrintTitlePipeline:
    async def put_item(self, item: Page) -> Page:
        print(f"[page] {item.url} — {item.title}")
        return item

    async def close(self): ...


@scraper
async def scrape(send_request: SendRequest):
    await send_request(Request(url="https://example.com", callback=parse))


async def parse(response: Response, pipeline: Pipeline):
    html = await response.text()
    match = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    title = match.group(1).strip() if match else "unknown"
    await pipeline(Page(url=response.url, title=title))
