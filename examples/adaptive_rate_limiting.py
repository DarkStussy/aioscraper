#!/usr/bin/env python3
"""
Adaptive rate limiting example using EWMA + AIMD algorithm.

Demonstrates:
- Automatic backoff when server returns 429/503 (rate limit errors)
- Gradual increase of request rate on sustained success
- Per-domain adaptive throttling
- Retry-After header respect

Run with:
    $ aioscraper adaptive_rate_limiting
"""

from aioscraper import AIOScraper
from aioscraper.config import AdaptiveRateLimitConfig, Config, RateLimitConfig, SessionConfig
from aioscraper.types import Request, Response, SendRequest

# Configure adaptive rate limiting
scraper = AIOScraper(
    config=Config(
        SessionConfig(
            rate_limit=RateLimitConfig(
                enabled=True,
                # Base interval between requests (starting point)
                default_interval=0.5,
                # Enable adaptive rate limiting
                adaptive=AdaptiveRateLimitConfig(
                    # Minimum interval (won't go below this)
                    min_interval=0.1,
                    # Maximum interval (won't go above this)
                    max_interval=10.0,
                    # Multiplicative increase on failure (429, 503, timeout)
                    # New interval = current_interval * increase_factor
                    increase_factor=2.0,
                    # Additive decrease on sustained success
                    # New interval = current_interval - decrease_step
                    decrease_step=0.05,
                    # Number of successes before decreasing interval
                    success_threshold=5,
                    # EWMA alpha for latency smoothing (0.0-1.0)
                    # Higher = more weight on recent latencies
                    ewma_alpha=0.3,
                    # Respect Retry-After header from server
                    respect_retry_after=True,
                    # Use same triggers as retry config (429, 503, timeouts)
                    inherit_retry_triggers=True,
                ),
            ),
        ),
    ),
)


@scraper
async def scrape(send_request: SendRequest):
    """
    Send multiple requests to demonstrate adaptive throttling.

    The rate limiter will:
    1. Start with 0.5s interval
    2. If server returns 429/503 -> multiply interval by 2.0 (backoff)
    3. After 5 consecutive successes -> decrease interval by 0.05 (probe for capacity)
    4. Respect Retry-After header if present
    """
    api_url = "https://api.github.com"

    # Send 20 requests to the same domain
    # Watch how interval adapts to server responses
    for i in range(20):
        await send_request(
            Request(
                url=f"{api_url}/users/octocat",
                callback=handle_response,
                # Store request number in context for tracking
                cb_kwargs={"request_num": i + 1},
            ),
        )


async def handle_response(response: Response, request_num: int):
    """Handle API response and track adaptive behavior."""
    print(f"✅ Request #{request_num}: {response.status} - {response.url}")

    # Note: The adaptive rate limiter automatically tracks:
    # - Response latency (EWMA smoothing)
    # - Success/failure (based on status codes)
    # - Server backoff signals (Retry-After header)
    #
    # You don't need to do anything in the callback!
