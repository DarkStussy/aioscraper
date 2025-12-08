# aioscraper

<p align="center">
  <img src="https://raw.githubusercontent.com/DarkStussy/aioscraper/main/docs/static/aioscraper.png" alt="aioscraper logo" width="340">
</p>

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![PyPI](https://img.shields.io/pypi/v/aioscraper)
![Tests](https://github.com/darkstussy/aioscraper/actions/workflows/tests.yml/badge.svg)
[![Documentation Status](https://readthedocs.org/projects/aioscraper/badge/?version=latest)](https://aioscraper.readthedocs.io/en/latest/)
![GitHub last commit](https://img.shields.io/github/last-commit/darkstussy/aioscraper)

### Asynchronous framework for building modular and scalable web scrapers.

> **Beta notice:** APIs and behavior may change; expect sharp edges while things settle.

## Key Features

- Async-first core with pluggable HTTP backends (`aiohttp`/`httpx`) and `aiojobs` scheduling
- Declarative flow: requests → callbacks → pipelines, with middleware hooks
- Priority queueing plus configurable concurrency
- Adaptive rate limiting with EWMA + AIMD algorithm - automatically backs off on server overload
- Small, explicit API that is easy to test and compose

## Getting started

Install
```bash
pip install "aioscraper[aiohttp]"
# or use httpx as the HTTP backend
pip install "aioscraper[httpx]"
```

Create `scraper.py`:
```python
from aioscraper import AIOScraper, Request, Response, SendRequest

scraper = AIOScraper()

@scraper
async def scrape(send_request: SendRequest):
    await send_request(Request(url="https://example.com", callback=handle_response))


async def handle_response(response: Response):
    print(f"Fetched {response.url} with status {response.status}")
```

Run it
```bash
aioscraper scraper
```

[Documentation](https://aioscraper.readthedocs.io)

## Why aioscraper?

- Scrapy is mature but tied to Twisted and a heavier, older stack. aioscraper is plain asyncio with modern typing and explicit control flow.
- Less magic: declarative Request → callback → pipeline without opaque spider classes; each piece is a normal function or typed class, simple to test and mock.
- Light footprint: pluggable HTTP backend (aiohttp/httpx), no global settings or hidden state, no vendor lock-in.
- Built for modern workloads: high-volume API/JSON crawling, fanning out to microservice endpoints, quick data collection jobs where you want async throughput without a large framework.
- Easy to embed: runs inside existing async apps (FastAPI, workers, cron jobs) without adapting to a separate runtime.

## Use cases

- Collecting data from many JSON/REST endpoints concurrently
- Fan-out calls inside microservices to hydrate/cache data
- Lightweight scraping jobs that should be easy to test and ship (no big framework overhead)
- Benchmarks show stable throughput across CPython 3.11–3.14 (see the [benchmarks](https://aioscraper.readthedocs.io/en/latest/benchmarks.html))

## Contributing

Please see the [Contributing guide](https://aioscraper.readthedocs.io/en/latest/contributing.html) for workflow, tooling, and review expectations.

## License

MIT License

Copyright (c) 2025 darkstussy
