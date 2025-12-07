Configuration
=============

`aioscraper` ships sane defaults but exposes configuration for sessions, scheduling, execution, and pipeline dispatching.

You can build a :class:`Config <aioscraper.config.models.Config>` and pass it to :class:`AIOScraper <aioscraper.core.scraper.AIOScraper>` via ``AIOScraper(config=...)``, or override values via :ref:`environment variables <cli-configuration>`.
The CLI reads well-known environment variables (for example ``SESSION_REQUEST_TIMEOUT``, ``SCHEDULER_CONCURRENT_REQUESTS``, ``EXECUTION_TIMEOUT``, ``PIPELINE_STRICT``) and applies them before launching the scraper.

The HTTP client is chosen at runtime: ``aiohttp`` is used when installed, otherwise ``httpx``. Install one of the extras from :doc:`/installation` so requests can be executed.
Set :class:`SessionConfig.http_backend <aioscraper.config.models.SessionConfig>` (or ``SESSION_HTTP_BACKEND``) to a value from :class:`HttpBackend <aioscraper.config.models.HttpBackend>` if you want to force one client even when both are available.


.. code-block:: python

    import logging
    from aioscraper import AIOScraper, run_scraper
    from aioscraper.config import (
        Config,
        SessionConfig,
        SchedulerConfig,
        ExecutionConfig,
        PipelineConfig,
        RateLimitConfig,
    )

    config = Config(
        session=SessionConfig(
            timeout=20,
            rate_limit=RateLimitConfig(default_interval=0.05),
            ssl=True,
            proxy="http://localhost:8080",
        ),
        scheduler=SchedulerConfig(concurrent_requests=32, pending_requests=4, close_timeout=0.5),
        execution=ExecutionConfig(
            timeout=60,
            shutdown_timeout=0.5,
            shutdown_check_interval=0.1,
            log_level=logging.WARNING,
        ),
        pipeline=PipelineConfig(strict=False),
    )


    async def main():
        scraper = AIOScraper(config=config)
        await run_scraper(scraper)

Graceful shutdown
-----------------

- ``execution.timeout`` — overall budget (``None`` by default, i.e. no total limit); on expiry the runner logs at ``execution.log_level`` and cancels all tasks.
- ``execution.shutdown_timeout`` — grace period after SIGINT/SIGTERM/timeout before hard cancelling in-flight work.
- ``execution.shutdown_check_interval`` — pause between drain checks while waiting for the scheduler/queue to empty.
- Signals: first SIGINT/SIGTERM initiates shutdown, second triggers force-exit. Lifespan is shielded so cleanup still runs.

These settings are honored by both the CLI and :func:`run_scraper <aioscraper.core.runner.run_scraper>`, giving consistent stop behavior in code or from the terminal.


.. _proxy-config:

Proxies
-------

:class:`SessionConfig.proxy <aioscraper.config.models.SessionConfig>` accepts two shapes; pick the one your HTTP client supports:

- ``aiohttp`` — ``"http://localhost:8000"`` (single proxy applied to every request).
- ``httpx`` (single proxy) — ``"http://localhost:8000"`` when one proxy handles all schemes.
- ``httpx`` (per-scheme) — ``{"http": "http://localhost:8000", "https": "http://localhost:8001"}`` to route ``http``/``https`` separately.

.. warning::

   ``httpx`` only supports client-scoped proxies, so per-request overrides are ignored. ``aiohttp`` does the opposite: a proxy passed directly in ``Request(..., proxy=...)`` takes precedence over ``config.session.proxy``.

Authentication
~~~~~~~~~~~~~~

Authenticated proxies can be provided by embedding credentials directly in the
proxy URL, for example:

``http://username:password@localhost:8030``

This works for both ``aiohttp`` and ``httpx`` proxy configurations.

.. _rate-limit-config:

Rate Limiting
-------------

Set :class:`SessionConfig.rate_limit <aioscraper.config.models.RateLimitConfig>` or override values via :ref:`environment variables <cli-configuration>` to enable built-in rate limiting.

Rate limiting groups requests by a key (by default, the URL hostname) and enforces a minimum interval between requests within each group. This helps avoid overwhelming target servers and getting blocked.

.. code-block:: python

   from aioscraper.config import RateLimitConfig

   rate_limit_config = RateLimitConfig(
       enabled=True,
       default_interval=0.5,  # 500ms between requests per host
       cleanup_timeout=60.0,  # Clean up idle groups after 60 seconds
   )

**Configuration options:**

- ``enabled``: Toggle rate limiting on or off (default: ``False``).
- ``group_by``: Custom function to group requests and specify per-group intervals. Must return ``tuple[Hashable, float]`` where the first element is the group key and the second is the interval in seconds.
- ``default_interval``: Default delay in seconds between requests within each group (default: ``0.0``).
- ``cleanup_timeout``: Timeout in seconds for cleaning up inactive request groups (default: ``60.0``).

Custom grouping
~~~~~~~~~~~~~~~

You can define custom grouping logic to apply different rate limits per domain or endpoint:

.. code-block:: python

   from yarl import URL
   from aioscraper.config import RateLimitConfig


   def custom_group_by(request):
      """Group by domain with custom intervals."""
      host = URL(request.url).host
      if host == "api.example.com":
         return (host, 0.1)  # 100ms for API
      elif host == "www.example.com":
         return (host, 1.0)  # 1 second for website

      return (host, 0.5)  # 500ms default


   rate_limit_config = RateLimitConfig(enabled=True, group_by=custom_group_by)

When ``enabled=False`` (default), group-based rate limiting is bypassed. However, if ``default_interval`` is set, it will still apply a simple delay between all requests without grouping logic.

.. _retry-config:

Retries
-------

Set :class:`SessionConfig.retry <aioscraper.config.models.SessionConfig>` or override values via :ref:`environment variables <cli-configuration>` to enable the built-in retry middleware.

You can pick the number of retry attempts, backoff strategy, status codes, exception types:

The ``backoff`` option accepts the following values:

- ``CONSTANT``: uses a fixed delay for every retry attempt.

- ``LINEAR``: delay increases linearly with each attempt:
  ``delay = base_delay * attempt``.

- ``EXPONENTIAL``: delay grows exponentially with each attempt:
  ``delay = base_delay * (2 ** attempt)``.

- ``EXPONENTIAL_JITTER``: exponential backoff with added randomness (jitter) to prevent thundering herd effects.

For ``EXPONENTIAL_JITTER``, the delay is calculated as follows:

.. code-block:: python

   delay = base_delay * (2 ** attempt)
   delay = (delay / 2) + random.uniform(0, delay / 2)

For both ``EXPONENTIAL`` and ``EXPONENTIAL_JITTER``, ``max_delay`` caps the final delay to avoid excessively long waits.


.. code-block:: python

   import asyncio
   from aioscraper.config import RequestRetryConfig, BackoffStrategy

   retry_config = RequestRetryConfig(
      enabled=True,
      attempts=5,
      backoff=BackoffStrategy.EXPONENTIAL_JITTER,
      base_delay=1.0,
      max_delay=5.0,
      statuses=(500, 502, 503),
      exceptions=(asyncio.TimeoutError,),
   )

When enabled, :class:`RetryMiddleware <aioscraper.middlewares.retry.RetryMiddleware>` is registered automatically as an exception middleware and reschedules the request through the internal queue.
You can override its priority/``stop_processing`` behaviour via ``RequestRetryConfig.middleware``.

Server-side Retry-After
~~~~~~~~~~~~~~~~~~~~~~~

When the server responds with a ``Retry-After`` header (RFC 9110), the middleware respects it and uses the server-specified delay instead of the configured backoff strategy. This only applies to ``429 Too Many Requests`` and ``503 Service Unavailable`` responses.

The ``Retry-After`` header can be specified as:

- **Seconds**: ``Retry-After: 120`` (wait 120 seconds)
- **HTTP-date**: ``Retry-After: Wed, 21 Oct 2015 07:28:00 GMT``

The delay from ``Retry-After`` is capped at 600 seconds (10 minutes) to prevent indefinite delays.


API
---

.. autoclass:: aioscraper.config.models.Config
   :members:
   :no-index:

.. autofunction:: aioscraper.config.loader.load_config
   :no-index:

.. autoclass:: aioscraper.config.models.SessionConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.models.RequestRetryConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.models.RateLimitConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.models.SchedulerConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.models.ExecutionConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.models.PipelineConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.models.MiddlewareConfig
   :members:
   :no-index: