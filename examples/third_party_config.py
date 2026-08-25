"""
Build the whole Config with a third-party loader instead of load_config().

Any loader that fills dataclasses from their annotations works, because Config holds only data -
group_by and should_retry are AIOScraper arguments, not config fields. The fields that name their
object indirectly need a converter: session.ssl takes a CA bundle path, and the exception tuples
take dotted paths.

This one uses dature, which needs Python 3.12 - one minor above aioscraper's own floor - and its
TOML extra:

    $ pip install "aioscraper[aiohttp]" "dature[toml]"

Write aioscraper.toml next to this file:

    [session]
    timeout = 20.0
    buffer_body = true
    ssl = "true"

    [session.retry]
    attempts = 5
    backoff = "exponential_jitter"
    exceptions = [
        "aioscraper.exceptions.TransportTimeout",
        "aioscraper.exceptions.ConnectionFailed",
    ]

    [session.rate_limit]
    per_group = true
    default_interval = 0.25

    [session.rate_limit.adaptive]
    max_interval = 3.0

    [scheduler]
    concurrent_requests = 128

Run it:

    $ python third_party_config.py
"""

import asyncio
import ssl

import dature

from aioscraper import AIOScraper, Request, Response, ScheduleRequest, run_scraper
from aioscraper.config import Config
from aioscraper.config.converters import parse_exception, parse_ssl

# the two fields a file can only name, not hold
TYPE_LOADERS = {ssl.SSLContext: parse_ssl, type[BaseException]: parse_exception}
TEAPOT = 418


def group_by(request: Request) -> tuple[str, float]:
    "Pace the API twice as fast as everything else."
    return ("api", 0.1) if "/api/" in request.url else ("web", 0.25)


def should_retry(request: Request, exc: Exception, retries: int) -> bool | None:
    "Retry a teapot, which no status list covers; None defers to the configured match."
    return True if getattr(exc, "status_code", None) == TEAPOT else None


def load() -> Config:
    """Read the TOML file, then let AIOSCRAPER_-prefixed variables override it.

    dature nests with a double underscore, so AIOSCRAPER_SESSION__RETRY__ATTEMPTS=9 sets
    session.retry.attempts. The names load_config() reads are unrelated and are not consulted here.
    The field validators run either way.
    """
    return dature.load(
        dature.Toml11Source(file="aioscraper.toml"),
        dature.EnvSource(prefix="AIOSCRAPER_"),
        schema=Config,
        type_loaders=TYPE_LOADERS,
    )


async def parse(response: Response):
    print(f"{response.status} {response.url}")


async def scrape(schedule_request: ScheduleRequest):
    await schedule_request(Request("https://api.github.com/repos/django/django", callback=parse))


async def main():
    config = load()
    print(f"timeout={config.session.timeout} attempts={config.session.retry.attempts}")
    print(f"exceptions={[exc.__name__ for exc in config.session.retry.exceptions]}")

    scraper = AIOScraper(scrape, config=config, group_by=group_by, should_retry=should_retry)
    result = await run_scraper(scraper)
    print(f"ok={result.ok} requests={result.requests_started}")


if __name__ == "__main__":
    asyncio.run(main())
