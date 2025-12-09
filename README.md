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

## Table of Contents

- [Key Features](#key-features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Examples](#examples)
- [Why aioscraper?](#why-aioscraper)
- [Use Cases](#use-cases)
- [Documentation](#documentation)
- [Contributing](#contributing)

## Key Features

- **Async-first** core with pluggable HTTP backends (`aiohttp`/`httpx`) and `aiojobs` scheduling
- **Declarative flow**: requests → callbacks → pipelines, with middleware hooks at each stage
- **Priority queueing** plus configurable concurrency limits per group
- **Adaptive rate limiting** with EWMA + AIMD algorithm - automatically backs off on server overload
- **Small, explicit API** that is easy to test and compose with existing async applications

## Installation

Choose your HTTP backend:

```bash
# Option 1: Use aiohttp (recommended for most cases)
pip install "aioscraper[aiohttp]"

# Option 2: Use httpx (if you prefer httpx ecosystem)
pip install "aioscraper[httpx]"

# Option 3: Install both backends for flexibility
pip install "aioscraper[aiohttp,httpx]"
```

## Quick Start

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

Run it:
```bash
aioscraper scraper
```

What's happening?

1. `@scraper` decorator registers the `scrape()` function as the entry point
2. `send_request()` schedules a request with a callback; requests are queued and executed with rate limiting
3. `callback=handle_response` is called when the response arrives; you can parse data, send new requests, or push items to pipelines
4. The `aioscraper` command finds `scraper.py`, starts the async runtime, and runs your scraper

## Examples

See the [examples/](examples/) directory for fully commented code demonstrating.

## Why aioscraper?

- Scrapy is mature but tied to Twisted and a heavier, older stack. aioscraper is plain asyncio with modern typing and explicit control flow.
- Less magic: declarative Request → callback → pipeline without opaque spider classes; each piece is a normal function or typed class, simple to test and mock.
- Light footprint: pluggable HTTP backend (aiohttp/httpx), no global settings or hidden state, no vendor lock-in.
- Built for modern workloads: high-volume API/JSON crawling, fanning out to microservice endpoints, quick data collection jobs where you want async throughput without a large framework.
- Easy to embed: runs inside existing async apps (FastAPI, workers, cron jobs) without adapting to a separate runtime.

## Use Cases

- **High-volume API/JSON crawling** - Collecting data from many REST endpoints concurrently with automatic rate limiting
- **Microservice integration** - Fan-out calls inside async apps to hydrate/cache data from external services
- **Lightweight scraping jobs** - Quick data collection tasks without heavy framework overhead
- **Embedded scraping** - Runs inside existing async apps (FastAPI, workers, cron jobs) without separate runtime

Performance: Benchmarks show stable throughput across CPython 3.11–3.14 (see [benchmarks](https://aioscraper.readthedocs.io/en/latest/benchmarks.html))

## Documentation

Full documentation at [aioscraper.readthedocs.io](https://aioscraper.readthedocs.io)

## Contributing

Please see the [Contributing guide](https://aioscraper.readthedocs.io/en/latest/contributing.html) for workflow, tooling, and review expectations.

## License

MIT License

Copyright (c) 2025 darkstussy
