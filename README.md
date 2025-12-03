# aioscraper

![aioscraper logo](docs/static/aioscraper.png)

**Asynchronous framework for building modular and scalable web scrapers.**

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Version](https://img.shields.io/github/v/tag/darkstussy/aioscraper?label=version)

## Features

- 🚀 Fully asynchronous architecture powered by `aiohttp` and `aiojobs`
- 🔧 Modular system with middleware support
- 📦 Pipeline data processing
- ⚙️ Flexible configuration
- 🔄 Priority-based request queue management
- 🛡️ Built-in error handling

## Basic usage

Install
```bash
pip install aioscraper
```

Example of fetching data.
```python
import asyncio

from aioscraper import AIOScraper
from aioscraper.types import Request, SendRequest, Response


async def scraper(send_request: SendRequest) -> None:
    await send_request(Request(url="https://example.com", callback=handle_response))


async def handle_response(response: Response) -> None:
    print(f"Fetched {response.url} with status {response.status}")


async def main():
    async with AIOScraper(scraper) as s:
        await s.start()


if __name__ == "__main__":
    asyncio.run(main())

```

## Benchmarks

Below are benchmarks comparing `aioscraper` and `scrapy` on a local JSON server.

The scripts used for these tests are available in [this Gist](https://gist.github.com/DarkStussy/7afd89d65a289d3d7128c9b74c68a76a).

### Benchmark 1
* Path: `/json?size=10`
* Total requests: 10,000
* Total items: 100,000

| Library    | Elapsed time | Requests per second | Items per second |
|------------|--------------|-------------------|----------------|
| aioscraper | 1.9 sec      | 5,263.2           | 52,631.6       |
| scrapy     | 26.8 sec     | 373.1             | 3,731.3        |

---

### Benchmark 2
* Path: `/json?size=100`
* Total requests: 10,000
* Total items: 1,000,000

| Library    | Elapsed time | Requests per second | Items per second |
|------------|--------------|-------------------|----------------|
| aioscraper | 3.1 sec      | 3,225.8           | 322,580.6      |
| scrapy     | 205.8 sec    | 48.6              | 4,859.1        |

---

### Benchmark 3
* Path: `/json?size=10&t=0.1`
* Total requests: 10,000
* Total items: 100,000

| Library    | Elapsed time | Requests per second | Items per second |
|------------|--------------|-------------------|----------------|
| aioscraper | 16.1 sec     | 621.1             | 6,211.2        |
| scrapy     | 129.9 sec    | 77.0              | 769.8          |

## License

MIT License

Copyright (c) 2025 darkstussy

## Links

- [PyPI](https://pypi.org/project/aioscraper)
- [GitHub](https://github.com/darkstussy/aioscraper)
- [Issues](https://github.com/darkstussy/aioscraper/issues)
