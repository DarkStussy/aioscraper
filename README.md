# aioscraper

<p align="center">
  <img src="https://raw.githubusercontent.com/DarkStussy/aioscraper/main/docs/static/aioscraper.png" alt="aioscraper logo" width="340">
</p>

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![GitHub License](https://img.shields.io/github/license/darkstussy/aioscraper?color=brightgreen)
[![PyPI - Version](https://img.shields.io/pypi/v/aioscraper?color=brightgreen)](https://pypi.org/project/aioscraper/)
[![PyPI - Downloads](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fshieldcn.dev%2Fpypi%2Fdm%2Faioscraper.json&query=%24.value&label=downloads&color=brightgreen&style=flat)](https://pypistats.org/packages/aioscraper)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/darkstussy/aioscraper/tests.yml?style=flat&label=Tests)
[![codecov](https://codecov.io/gh/darkstussy/aioscraper/branch/main/graph/badge.svg)](https://codecov.io/gh/darkstussy/aioscraper)
[![Read the Docs](https://img.shields.io/readthedocs/aioscraper?color=brightgreen)](https://aioscraper.readthedocs.io/)
![GitHub last commit](https://img.shields.io/github/last-commit/darkstussy/aioscraper?color=brightgreen)

### High-performance asynchronous Python framework for large-scale API data collection.

**API-first.** aioscraper orchestrates thousands of concurrent JSON/REST calls with adaptive rate
limiting, retries, priority queues and item pipelines. Selectors and a crawling engine are not part
of the core - plug in your own parser if you need one (see [examples/quotes.py](examples/quotes.py)).

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

- **Async-first** core with pluggable HTTP backends (`aiohttp`/`httpx`/`httpx2`) and `aiojobs` scheduling
- **Declarative flow**: requests → callbacks → pipelines, with middleware hooks at each stage
- **Priority queueing** with backpressure, a global concurrency limit and per-group rate limits
- **Adaptive rate limiting** with EWMA + AIMD algorithm - automatically backs off on server overload
- **Small, explicit API** that is easy to test and compose with existing async applications

## Installation

Choose your HTTP backend:

```bash
# Option 1: Use aiohttp (recommended for most cases)
pip install "aioscraper[aiohttp]"

# Option 2: Use httpx (if you prefer httpx ecosystem)
pip install "aioscraper[httpx]"

# Option 3: Use httpx2, the Pydantic-maintained fork of httpx
pip install "aioscraper[httpx2]"

# Option 4: Install several backends for flexibility
pip install "aioscraper[aiohttp,httpx,httpx2]"
```

## Quick Start

Create `scraper.py`:
```python
import logging
from aioscraper import AIOScraper, Request, Response, ScheduleRequest, Pipeline
from dataclasses import dataclass

logger = logging.getLogger("github_repos")
scraper = AIOScraper()


@dataclass(slots=True)
class RepoStats:
    name: str
    stars: int
    language: str


# registers the pipeline that handles RepoStats items
@scraper.pipeline(RepoStats)
class StatsPipeline:
    def __init__(self):
        self.total_stars = 0

    async def put_item(self, item: RepoStats) -> RepoStats:
        # runs once per extracted item: store it, queue it, validate it, or aggregate as here
        self.total_stars += item.stars
        logger.info("✓ %s: ⭐ %s (%s)", item.name, item.stars, item.language)
        return item

    async def close(self):
        # runs once when the scraper stops: flush buffers, close connections, report totals
        logger.info("Total stars collected: %s", self.total_stars)


# registers an entry point; schedule_request is injected by parameter name
@scraper
async def get_repos(schedule_request: ScheduleRequest):
    repos = (
        "django/django",
        "fastapi/fastapi",
        "pallets/flask",
        "encode/httpx",
        "aio-libs/aiohttp",
    )

    for repo in repos:
        await schedule_request(
            Request(
                url=f"https://api.github.com/repos/{repo}",
                callback=parse_repo,  # runs on a response with a status below 400
                errback=on_failure,  # runs on anything else: 4xx/5xx, timeouts, connection failures
                cb_kwargs={"repo": repo},  # extra arguments for both of them
                headers={"Accept": "application/vnd.github+json"},  # required by the GitHub API
            )
        )


async def parse_repo(response: Response, pipeline: Pipeline):
    # the body has to be read here: the connection is released when the callback returns
    data = await response.json()
    await pipeline(
        RepoStats(
            name=data["full_name"],
            stars=data["stargazers_count"],
            language=data.get("language", "Unknown"),
        )
    )


async def on_failure(exc: Exception, repo: str):
    logger.error("%s: cannot parse response: %s", repo, exc)
```

Run it:
```bash
aioscraper scraper
```

What's happening?

1. `@scraper` registers the entry point; `@scraper.pipeline` registers a pipeline for `RepoStats`
2. `schedule_request()` queues a request and returns; the framework dispatches it when a slot frees up
3. Requests run concurrently up to the limit, so responses arrive in no particular order
4. `parse_repo` handles each response, `on_failure` handles each failure that was not retried
5. `StatsPipeline.close()` runs once at the end, after every request has finished

Retries are on by default. Rate limiting is not - turn it on, along with concurrency and timeouts, through
[environment variables](https://aioscraper.readthedocs.io/en/latest/cli.html#configuration) before running this against a real API.

## Examples

Runnable, commented scrapers live in [examples/](examples/).

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
