# aioscraper

<p align="center">
  <img src="docs/static/aioscraper.png" alt="aioscraper logo" width="340">
</p>

### Asynchronous framework for building modular and scalable web scrapers.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![PyPI](https://img.shields.io/pypi/v/aioscraper)
![Tests](https://github.com/darkstussy/aioscraper/actions/workflows/tests.yml/badge.svg)
[![Documentation Status](https://readthedocs.org/projects/aioscraper/badge/?version=latest)](https://aioscraper.readthedocs.io/en/latest/)
![GitHub last commit](https://img.shields.io/github/last-commit/darkstussy/aioscraper)

> **Beta notice:** APIs and behavior may change; expect sharp edges while things settle.

## Key Features

- Fully asynchronous architecture with `aiojobs` scheduling and pluggable HTTP backends (`aiohttp` preferred, `httpx` supported)
- Modular system with middleware support
- Pipeline data processing
- Flexible configuration
- Priority-based request queue management
- Built-in error handling

[Documentation](https://aioscraper.readthedocs.io)

## Getting started

Install
```bash
pip install "aioscraper[aiohttp]"
# or use httpx as the HTTP backend
pip install "aioscraper[httpx]"
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

## License

MIT License

Copyright (c) 2025 darkstussy
