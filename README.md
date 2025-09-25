# aioscraper

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

## Installation

```bash
pip install aioscraper
```

## Requirements

- Python 3.10 or higher
- aiohttp
- aiojobs

## Quick Start

```python
import asyncio

from aioscraper import AIOScraper
from aioscraper.types import Response, RequestSender


async def scrapper(send_request: RequestSender) -> None:
    await send_request(url="https://example.com", callback=handle_response)


async def handle_response(response: Response) -> None: ...


async def main():
    async with AIOScraper(scrapers=[scrapper]) as scraper:
        await scraper.start()


if __name__ == "__main__":
    asyncio.run(main())

```

## License

MIT License

Copyright (c) 2025 darkstussy

## Links

- [PyPI](https://pypi.org/project/aioscraper)
- [GitHub](https://github.com/darkstussy/aioscraper)
- [Issues](https://github.com/darkstussy/aioscraper/issues)
