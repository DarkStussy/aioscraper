# aioscraper

![aioscraper logo](docs/static/aioscraper.png)

**Asynchronous framework for building modular and scalable web scrapers.**

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Version](https://img.shields.io/github/v/tag/darkstussy/aioscraper?label=version)

## Key Features

- Fully asynchronous architecture powered by `aiohttp` and `aiojobs`
- Modular system with middleware support
- Pipeline data processing
- Flexible configuration
- Priority-based request queue management
- Built-in error handling

[Documentation](https://aioscraper.readthedocs.io)

## Getting started

Install
```bash
pip install aioscraper
```

Create `scraper.py`:
```python
from aioscraper import AIOScraper
from aioscraper.types import Request, Response, SendRequest

scraper = AIOScraper()

@scraper.register
async def scrape(send_request: SendRequest):
    await send_request(Request(url="https://example.com", callback=handle_response))


async def handle_response(response: Response):
    print(f"Fetched {response.url} with status {response.status}")
```

Run it
```bash
aioscraper scraper
```

## Benchmarks

Below are benchmarks comparing `aioscraper` and `scrapy` on a local JSON server.

The scripts used for these tests are available in [this Gist](https://gist.github.com/DarkStussy/dc5d3c2b4029428e990ad44190f4cdbc).

## License

MIT License

Copyright (c) 2025 darkstussy
