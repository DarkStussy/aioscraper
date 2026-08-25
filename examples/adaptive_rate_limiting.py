"""
Adaptive rate limiting: each group finds its own pace instead of holding the configured one.

The interval starts at default_interval and moves from what the responses look like - multiplied on
pushback, stepped back down after a run of successes. Every field below is at its default except
the intervals; see docs/concepts/config.rst for what each one does.

Run it:

    $ aioscraper adaptive_rate_limiting
"""

from aioscraper import AIOScraper
from aioscraper.config import AdaptiveRateLimitConfig, Config, RateLimitConfig, SessionConfig
from aioscraper.types import Request, Response, ScheduleRequest

scraper = AIOScraper(
    config=Config(
        session=SessionConfig(
            rate_limit=RateLimitConfig(
                per_group=True,  # required: adaptive paces a group at a time
                default_interval=0.5,
                adaptive=AdaptiveRateLimitConfig(
                    min_interval=0.1,
                    max_interval=10.0,
                    increase_factor=2.0,
                    decrease_step=0.05,
                    success_threshold=5,
                    ewma_alpha=0.3,
                    respect_retry_after=True,
                    inherit_retry_triggers=True,
                ),
            ),
        ),
    ),
)


@scraper
async def scrape(schedule_request: ScheduleRequest):
    "Enough requests to one host that the interval has room to move."
    for i in range(20):
        await schedule_request(
            Request(
                "https://api.github.com/users/octocat",
                callback=handle_response,
                cb_kwargs={"request_num": i + 1},
            ),
        )


async def handle_response(response: Response, request_num: int):
    # the callback does nothing for the rate limiter: latency and status are recorded for it
    print(f"Request #{request_num}: {response.status} - {response.url}")
