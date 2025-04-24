# aioscraper

**Asynchronous framework for building modular and scalable web scrapers.**

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/github/license/darkstussy/aioscraper)
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

from aioscraper import BaseScraper, AIOScraper
from aioscraper.types import Response, RequestSender


class Scraper(BaseScraper):
    async def start(self, send_request: RequestSender) -> None:
        await send_request(url="https://example.com", callback=self.parse)

    async def parse(self, response: Response) -> None:
        # handle response
        pass


async def main():
    async with AIOScraper(scrapers=[Scraper()]) as scraper:
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
