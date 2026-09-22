# aioscraper

<p align="center">
  <img src="https://raw.githubusercontent.com/DarkStussy/aioscraper/main/docs/static/aioscraper.png" alt="aioscraper logo" width="340">
</p>

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![GitHub License](https://img.shields.io/github/license/darkstussy/aioscraper?color=brightgreen)
[![PyPI - Version](https://img.shields.io/pypi/v/aioscraper?color=brightgreen)](https://pypi.org/project/aioscraper/)
[![PyPI - Downloads](https://img.shields.io/pepy/dt/aioscraper?style=flat&label=downloads&color=brightgreen)](https://pepy.tech/project/aioscraper)
![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/darkstussy/aioscraper/tests.yml?style=flat&label=Tests)
[![codecov](https://codecov.io/gh/darkstussy/aioscraper/branch/main/graph/badge.svg)](https://codecov.io/gh/darkstussy/aioscraper)
[![Read the Docs](https://img.shields.io/readthedocs/aioscraper?color=brightgreen)](https://aioscraper.readthedocs.io/)
![GitHub last commit](https://img.shields.io/github/last-commit/darkstussy/aioscraper?color=brightgreen)

### An async Python framework for collecting data from APIs.

You write requests and response handlers. aioscraper queues the requests, limits concurrency, and
retries failed attempts. It has no selectors and no crawling engine - parse the response however you
like, with BeautifulSoup or anything else (see [examples/quotes.py](examples/quotes.py)).

It is worth reaching for when one process has to keep hundreds or thousands of requests in flight
and you would otherwise be writing that machinery yourself. For a handful of requests, use
`aiohttp` or `httpx` directly.

> **Beta:** APIs and behavior still change between releases. Pin the version.

## Installation

The core ships without an HTTP client, so pick one:

```bash
pip install "aioscraper[aiohttp]"  # or [httpx], or [httpx2] - the Pydantic fork of httpx
```

With one installed it is picked up automatically. Install several
(`"aioscraper[aiohttp,httpx]"`) and `SESSION_HTTP_BACKEND` chooses between them - otherwise
`aiohttp` wins. `[aiohttp-speedups]` is the same backend plus aiohttp's own speedups extra:
`aiodns`, `Brotli` and `backports.zstd`.

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
The settings that matter most at that point:

- `SCHEDULER_CONCURRENT_REQUESTS` - how many requests are in flight at once, 64 by default.
- `SCHEDULER_READY_QUEUE_MAX_SIZE` - blocks the entrypoint once this many scheduled requests are
  waiting, so a producer cannot queue work faster than the scraper gets through it. Defaults to `0`
  (unlimited). Only blocks scheduling from the entrypoint.
- `SESSION_RATE_LIMIT_INTERVAL` with `SESSION_RATE_LIMIT_PER_GROUP` - the delay between requests,
  applied per group (by hostname, unless `AIOScraper(group_by=...)` says otherwise).
- `SESSION_RATE_LIMIT_ADAPTIVE_ENABLED` - enables adaptive rate limiting. Requires
  `SESSION_RATE_LIMIT_PER_GROUP=true`. Increases the delay after configured errors and reduces it
  after consecutive successes.

The CLI is one way to run a scraper; `run_scraper()` and the async context manager are the others,
so aioscraper can also live inside a service you already have - see
[examples/web_service.py](examples/web_service.py).

## Examples

Runnable, commented scrapers live in [examples/](examples/):

- [quotes.py](examples/quotes.py) - paginated HTML scraping with BeautifulSoup
- [adaptive_rate_limiting.py](examples/adaptive_rate_limiting.py) - adjusting the interval per host from the responses
- [queue_consumer.py](examples/queue_consumer.py) - a long-running worker fed by Redis Pub/Sub
- [web_service.py](examples/web_service.py) - one scraper embedded in a FastAPI app
- [third_party_config.py](examples/third_party_config.py) - building `Config` with an external loader

## How it compares

**Scrapy** is a crawler: selectors, link following, and a large ecosystem of built-in middleware. Use
it to walk a website. aioscraper targets collecting data from APIs - it parses nothing for you, and
a callback can schedule further requests from what it read, as [quotes.py](examples/quotes.py) does
to follow pagination. It is plain asyncio, so it drops into an existing async app instead of owning
the process.

**`aiohttp` or `httpx` with your own semaphore and retry loop** works fine until you need per-group
pacing, backpressure between the producer and the fetchers, backoff that respects `Retry-After`, and
somewhere to put the results. That is roughly the code aioscraper already contains.

## Performance

Throughput is stable across CPython 3.11-3.14; the numbers and the harness are in the
[benchmarks](https://aioscraper.readthedocs.io/en/latest/benchmarks.html).

## Documentation

Full documentation at [aioscraper.readthedocs.io](https://aioscraper.readthedocs.io)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and release notes.

## Contributing

Please see the [Contributing guide](https://aioscraper.readthedocs.io/en/latest/contributing.html) for workflow, tooling, and review expectations.

## License

MIT License

Copyright (c) 2025 darkstussy
