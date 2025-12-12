# aioscraper

<p align="center">
  <img src="https://raw.githubusercontent.com/DarkStussy/aioscraper/main/docs/static/aioscraper.png" alt="aioscraper logo" width="340">
</p>

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![GitHub License](https://img.shields.io/github/license/darkstussy/aioscraper?color=brightgreen)
[![PyPI - Version](https://img.shields.io/pypi/v/aioscraper?color=brightgreen)](https://pypi.org/project/aioscraper/)
![PyPI - Downloads](https://img.shields.io/pypi/dm/aioscraper?style=flat&color=brightgreen)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/darkstussy/aioscraper/tests.yml?style=flat&label=Tests)
[![Read the Docs](https://img.shields.io/readthedocs/aioscraper?color=brightgreen)](https://aioscraper.readthedocs.io/)
![GitHub last commit](https://img.shields.io/github/last-commit/darkstussy/aioscraper?color=brightgreen)

### High-performance asynchronous Python framework for large-scale API data collection.

> **Beta notice:** APIs and behavior may change; expect sharp edges while things settle.

## Table of Contents

- [What is aioscraper?](#what-is-aioscraper)
- [Key Features](#key-features)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Examples](#examples)
- [Why aioscraper?](#why-aioscraper)
- [Use Cases](#use-cases)
- [Performance](#performance)
- [Documentation](#documentation)
- [Changelog](#changelog)
- [Contributing](#contributing)

## What is aioscraper?

aioscraper is an async Python framework designed for **mass data collection from APIs** and external services at scale.

**Built for:**
- Fetching data from hundreds/thousands of REST API endpoints concurrently
- Integrating multiple external services (payment gateways, analytics APIs, etc.)
- Building data aggregation pipelines from heterogeneous API sources
- Queue-based scraping workers consuming tasks from Redis/RabbitMQ
- Microservice fan-out requests with automatic rate limiting and retries

**NOT built for:**
- Parsing HTML/CSS (but nothing stops you from using BeautifulSoup if you want - see [examples/quotes.py](examples/quotes.py))
- Single API requests (use httpx or aiohttp directly)
- GraphQL or WebSocket scraping (different paradigm)

**Think:** "I need to fetch data from 10,000 product API endpoints" or "I need to poll 50 microservices every minute" → aioscraper is for you.

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
import logging
from aioscraper import AIOScraper, Request, Response, SendRequest, Pipeline
from dataclasses import dataclass

logger = logging.getLogger("github_repos")
scraper = AIOScraper()


@dataclass(slots=True)
class RepoStats:
    """Data model for extracted repository stats."""

    name: str
    stars: int
    language: str


# this decorator registers this pipeline to handle RepoStats items
@scraper.pipeline(RepoStats)
class StatsPipeline:
    """Pipeline for processing extracted repository data."""

    def __init__(self):
        self.total_stars = 0

    async def put_item(self, item: RepoStats) -> RepoStats:
        """
        Called for each extracted item.

        This is where you'd:
        - Save to database
        - Send to message queue
        - Perform validation/transformation
        - Aggregate statistics
        """
        self.total_stars += item.stars
        logger.info("✓ %s: ⭐ %s (%s)", item.name, item.stars, item.language)
        return item

    async def close(self):
        """
        Called when scraper shuts down.

        Use for:
        - Final aggregations
        - Closing database connections
        - Cleanup operations
        """
        logger.info("Total stars collected: %s", self.total_stars)


# this decorator marks this as the scraper's entry point.
@scraper
async def get_repos(send_request: SendRequest):
    """
    Entry point: defines what to scrape.

    Receives send_request - a function to schedule HTTP requests.
    """
    repos = (
        "django/django",
        "fastapi/fastapi",
        "pallets/flask",
        "encode/httpx",
        "aio-libs/aiohttp",
    )

    for repo in repos:
        await send_request(
            Request(
                url=f"https://api.github.com/repos/{repo}",  # API endpoint
                callback=parse_repo,  # Success handler
                errback=on_failure,  # Error handler (network failures, timeouts)
                cb_kwargs={"repo": repo},  # Additional arguments to pass to callbacks
                headers={"Accept": "application/vnd.github+json"},  # Required by GitHub API
            )
        )


async def parse_repo(response: Response, pipeline: Pipeline):
    """
    Success callback: parse response and extract data.

    The `pipeline` dependency is automatically injected by aioscraper.
    """
    data = await response.json()  # Parse JSON response from API
    await pipeline(  # Send extracted item to pipeline
        RepoStats(
            name=data["full_name"],
            stars=data["stargazers_count"],
            language=data.get("language", "Unknown"),
        )
    )


async def on_failure(exc: Exception, repo: str):
    """
    Error callback: handle request/processing failures.

       Use for:
       - Logging errors
       - Sending alerts
       - Custom retry logic
       """
       logger.error("%s: cannot parse response: %s", repo, exc)
```

Run it:
```bash
aioscraper scraper
```

What's happening?

1. `@scraper` registers your entry point
3. `@scraper.pipeline` registers a pipeline for processing extracted data
4. `send_request()` schedules multiple API requests concurrently with automatic queuing
5. `callback=parse_repo` processes successful responses, `errback=on_failure` handles errors

Recommendation:

Configure [retries, rate limiting, concurrency](https://aioscraper.readthedocs.io/en/latest/cli.html#configuration) via environment variables for production use.

## Examples

See the [examples/](examples/) directory for fully commented code demonstrating.

## Why aioscraper?

**vs Scrapy:**
- Scrapy is built for HTML scraping with CSS/XPath selectors and website crawling
- aioscraper is optimized for **API data collection** (JSON, REST, microservices)
- Native asyncio (no Twisted), modern type hints, minimal footprint
- Easily embeds into existing async applications

**vs httpx/aiohttp directly:**
- Manual approach: you handle rate limiting, retries, queuing, concurrency, backpressure
- aioscraper: adaptive rate limits, priority queues, pipelines, middleware out of the box
- Declarative Request → callback → pipeline instead of imperative control flow

**vs building custom async workers:**
- Less boilerplate: focus on business logic, not infrastructure
- Production-ready components: EWMA+AIMD rate limiting, graceful shutdown, dependency injection
- Testable: explicit dependencies, no global state, easy mocking

**When to use aioscraper:**
- Collecting data from 100+ API endpoints
- Fan-out calls to microservices for data enrichment
- Queue consumers processing API scraping tasks
- API aggregation/monitoring pipelines
- High-throughput data collection jobs

## Use Cases

### 1. E-commerce price monitoring
Poll 10,000 product API endpoints across multiple marketplaces:
- Adaptive rate limiting prevents bans
- Priority queue for trending products
- Pipeline aggregates prices → saves to DB → sends alerts on changes

### 2. Cryptocurrency data aggregation
Collect real-time prices from 20+ exchange APIs:
- Concurrent requests with per-exchange rate limits
- Built-in retry for transient failures
- Pipeline normalizes data formats → writes to time-series DB

### 3. Microservice data hydration
Your FastAPI app needs data from 50 internal services:
- Embed aioscraper in your async application
- Fan-out concurrent requests with backpressure control
- Middleware for auth, logging, circuit breaking

### 4. Queue-based scraping workers
Distributed architecture with Redis/RabbitMQ/SQS:
- Message queue publishes scraping tasks (URLs + params)
- aioscraper workers consume queue → fetch data → process
- Pipeline acknowledges messages after successful processing

### 5. Social media API aggregation
Aggregate user stats from Twitter, LinkedIn, GitHub APIs:
- Different rate limits per platform (adaptive throttling)
- Error callbacks for quota exceeded / auth failures
- Pipeline deduplicates → enriches → stores to database

### 6. Multi-source data snapshots
Collect point-in-time data from 500+ API sources simultaneously:
- Health monitoring: poll status endpoints of distributed services every minute
- Market data: snapshot prices from 200+ suppliers at exact intervals
- Analytics aggregation: fetch metrics from dozens of analytics APIs on schedule
- Concurrent execution with precise timing and automatic retries for failed sources

## Performance

Benchmarks show stable throughput across CPython 3.11–3.14 (see [benchmarks](https://aioscraper.readthedocs.io/en/latest/benchmarks.html))

## Documentation

Full documentation at [aioscraper.readthedocs.io](https://aioscraper.readthedocs.io)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and release notes.

## Contributing

Please see the [Contributing guide](https://aioscraper.readthedocs.io/en/latest/contributing.html) for workflow, tooling, and review expectations.

## License

MIT License

Copyright (c) 2025 darkstussy
