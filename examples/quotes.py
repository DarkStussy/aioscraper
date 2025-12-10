#!/usr/bin/env python3
"""
Scrape quotes.toscrape.com with BeautifulSoup: collect quotes, authors, and tags across pages.

Requires beautifulsoup4:

    $ pip install "aioscraper[aiohttp]" beautifulsoup4

Run with the CLI:

    $ aioscraper quotes
"""

from dataclasses import dataclass, field
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from aioscraper import AIOScraper
from aioscraper.types import Pipeline, Request, Response, SendRequest

START_URL = "https://quotes.toscrape.com/"
MAX_PAGE = 3

scraper = AIOScraper()


@dataclass(slots=True)
class Quote:
    text: str
    author: str
    tags: list[str] = field(default_factory=list)


@scraper.pipeline(Quote)
class CollectQuotes:
    def __init__(self):
        self.counter = 0

    async def put_item(self, item: Quote) -> Quote:
        self.counter += 1
        tag_list = ", ".join(item.tags) if item.tags else "no tags"
        print(f"“{item.text}” - {item.author} [{tag_list}]")
        return item

    async def close(self):
        print(f"Collected {self.counter} quotes")


@scraper
async def scrape(send_request: SendRequest):
    await send_request(Request(url=START_URL, callback=parse))


async def parse(response: Response, send_request: SendRequest, pipeline: Pipeline, page: int = 1):
    soup = BeautifulSoup(await response.text(), "html.parser")

    for block in soup.select(".quote"):
        text_el = block.select_one(".text")
        author_el = block.select_one(".author")
        tags = [tag.get_text(strip=True) for tag in block.select(".tags .tag")]

        if not text_el or not author_el:
            continue

        await pipeline(Quote(text=text_el.get_text(strip=True), author=author_el.get_text(strip=True), tags=tags))

    next_link = soup.select_one("li.next a")
    if next_link and page < MAX_PAGE:  # follow a couple of pages as an example
        next_url = urljoin(response.url, str(next_link.get("href") or ""))
        await send_request(Request(url=next_url, callback=parse, cb_kwargs={"page": page + 1}))
