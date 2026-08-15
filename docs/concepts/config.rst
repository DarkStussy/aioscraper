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
        ErrorPolicy,
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
        scheduler=SchedulerConfig(
            concurrent_requests=32,
            pending_requests=4,
            close_timeout=0.5,
            ready_queue_max_size=1000,
        ),
        execution=ExecutionConfig(
            timeout=60,
            shutdown_timeout=0.5,
            shutdown_check_interval=0.1,
            on_error=ErrorPolicy.FAIL,
            log_level=logging.WARNING,
        ),
        pipeline=PipelineConfig(strict=False),
    )


    async def main():
        scraper = AIOScraper(config=config)
        await run_scraper(scraper)

Graceful shutdown
-----------------

- ``execution.timeout`` - overall budget (``None`` by default, i.e. no total limit); on expiry the runner logs at ``execution.log_level`` and cancels all tasks.
- ``execution.shutdown_timeout`` - grace period after SIGINT/SIGTERM/timeout before hard cancelling in-flight work.
- ``execution.shutdown_check_interval`` - pause between drain checks while waiting for the scheduler/queue to empty.
- Signals: first SIGINT/SIGTERM initiates shutdown, second triggers force-exit. Lifespan is shielded so cleanup still runs.

Unhandled errors
----------------

A request that fails without an ``errback``, a failing ``errback``, and a resource that will not close are
logged and then dropped so the rest of the run continues. A failure handled by your own ``errback`` is
not recorded: handling it is the point of the callback.

They are also recorded on the scraper:

- :attr:`AIOScraper.error_counts <aioscraper.core.scraper.AIOScraper.error_counts>` - exact totals per context.
- :attr:`AIOScraper.errors <aioscraper.core.scraper.AIOScraper.errors>` - the most recent exceptions, capped so
  a run failing millions of requests does not keep every traceback alive.

``execution.on_error`` is applied by the **CLI only**, as an exit code:

- ``ErrorPolicy.LOG`` (default) - exit ``0`` regardless.
- ``ErrorPolicy.FAIL`` - exit ``1`` when anything was recorded.

Stopping the CLI with SIGINT/SIGTERM exits with ``130``, which takes precedence over both.

:func:`run_scraper <aioscraper.core.runner.run_scraper>` does not act on the policy: it returns ``True`` when a
signal stopped the run, and leaves the decision to you. Read ``error_counts`` after it returns.

The shutdown settings above are honored by both the CLI and ``run_scraper``, giving consistent stop behavior in
code or from the terminal.


.. _body-limits:

Body limits
-----------

Two independent caps bound how much of a response ends up in memory:

- ``max_response_body_size`` (``SESSION_MAX_RESPONSE_BODY_SIZE``) applies to bodies handed to callbacks,
  through both :meth:`read() <aioscraper.types.session.Response.read>` and :meth:`iter_bytes()
  <aioscraper.types.session.Response.iter_bytes>`. It raises :class:`ResponseTooLarge
  <aioscraper.exceptions.ResponseTooLarge>` at the chunk that crosses it, so the rest is never pulled from
  the socket. Defaults to ``None`` - unlimited.
- ``max_error_body_size`` (``SESSION_MAX_ERROR_BODY_SIZE``) applies to a failed response, whose body is read
  only to fill the :class:`HTTPException <aioscraper.exceptions.HTTPException>` message. Defaults to 64 KiB;
  a longer body is cut at the limit and the message ends with ``[truncated]``. ``0`` skips reading it.

.. code-block:: python

    from aioscraper.config import SessionConfig

    session_config = SessionConfig(
        max_response_body_size=32 * 1024 * 1024,
        max_error_body_size=8 * 1024,
    )

The error cap is separate and on by default: an endpoint answering ``500`` with gigabytes of HTML would
otherwise be buffered whole to build an error message.

See :ref:`reading the response body <response-body>` for the streaming contract these limits apply to.

.. _proxy-config:

Proxies
-------

:class:`SessionConfig.proxy <aioscraper.config.models.SessionConfig>` accepts two shapes; pick the one your HTTP client supports:

- ``aiohttp`` - ``"http://localhost:8000"`` (single proxy applied to every request).
- ``httpx`` (single proxy) - ``"http://localhost:8000"`` when one proxy handles all schemes.
- ``httpx`` (per-scheme) - ``{"http": "http://localhost:8000", "https": "http://localhost:8001"}`` to route ``http``/``https`` separately.

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
- ``adaptive``: Enable :ref:`adaptive rate limiting <adaptive-rate-limiting>` (default: ``None``).


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

.. _adaptive-rate-limiting:

Adaptive Rate Limiting
~~~~~~~~~~~~~~~~~~~~~~~

The adaptive rate limiting feature automatically adjusts request intervals based on server responses, using a hybrid **EWMA (Exponentially Weighted Moving Average) + AIMD (Additive Increase Multiplicative Decrease)** algorithm inspired by TCP congestion control.

How it works:

- Fast multiplicative increase on server overload (429, 503, timeouts) - backs off aggressively to avoid hammering struggling servers
- Slow additive decrease on sustained success - gradually probes for increased capacity
- Respects Retry-After headers - server-provided backoff takes priority over heuristics
- Per-group adaptation - each hostname/group adapts independently

.. code-block:: python

   from aioscraper.config import RateLimitConfig, AdaptiveRateLimitConfig

   rate_limit_config = RateLimitConfig(
       enabled=True,
       default_interval=0.1,  # Starting interval: 100ms
       adaptive=AdaptiveRateLimitConfig(
           min_interval=0.001,        # Min: 1ms (won't go below)
           max_interval=5.0,          # Max: 5s (won't exceed)
           increase_factor=2.0,       # Double interval on failure
           decrease_step=0.01,        # Subtract 10ms on success
           success_threshold=5,       # Decrease after 5 consecutive successes
           ewma_alpha=0.3,            # Latency smoothing factor
           respect_retry_after=True,  # Honor server Retry-After headers
       ),
   )

**Configuration options:**

- ``min_interval``: Minimum allowed interval in seconds (default: ``0.001``)
- ``max_interval``: Maximum allowed interval in seconds (default: ``5.0``)
- ``increase_factor``: Multiplicative factor for interval increase on failure (default: ``2.0``)
- ``decrease_step``: Additive step for interval decrease on success in seconds (default: ``0.01``)
- ``success_threshold``: Number of consecutive successes before decreasing interval (default: ``5``)
- ``ewma_alpha``: Smoothing factor for latency EWMA, between 0 and 1 (default: ``0.3``)
- ``respect_retry_after``: Use ``Retry-After`` header as override (default: ``True``)
- ``inherit_retry_triggers``: Inherit trigger statuses/exceptions from :ref:`retry config <retry-config>` (default: ``True``)

**Behavior:**

When a request fails with a trigger status (429, 500, 502, 503, 504, etc.) or exception (timeout):

1. If ``Retry-After`` header present and ``respect_retry_after=True`` → use that value
2. Otherwise, multiply current interval by ``increase_factor`` (e.g., 0.1s → 0.2s → 0.4s)

When requests succeed consistently:

1. After ``success_threshold`` consecutive successes, subtract ``decrease_step`` from interval
2. This gradually probes for increased capacity (e.g., 0.4s → 0.39s → 0.38s)

**Example scenario:**

.. code-block:: text

   Time    Event                  Interval
   ----    -----                  --------
   0.0s    Start                  0.100s (default)
   0.1s    Request #1 → 429       0.100s → 0.200s (×2)
   0.3s    Request #2 → 503       0.200s → 0.400s (×2)
   0.7s    Request #3 → 200 OK    0.400s (no change, count=1)
   1.1s    Request #4 → 200 OK    0.400s (no change, count=2)
   ...     (3 more successes)     ...
   2.7s    Request #8 → 200 OK    0.400s → 0.390s (count≥5, -0.01)
   3.1s    Request #9 → 200 OK    0.390s (no change, count=1)

**Integration with retry middleware:**

When both adaptive rate limiting and :ref:`retry middleware <retry-config>` are enabled:

- **Retry middleware** handles retry logic (attempts, backoff)
- **Adaptive rate limiter** adjusts the *sending rate* to prevent future failures
- Trigger statuses/exceptions are shared when ``inherit_retry_triggers=True``

This prevents the system from repeatedly hammering an overloaded server while retries are ongoing.

.. _retry-config:

Retries
-------

Set :class:`SessionConfig.retry <aioscraper.config.models.SessionConfig>` or override values via :ref:`environment variables <cli-configuration>` to enable the built-in retry middleware.

You can pick the number of retry attempts, backoff strategy, status codes, exception types, HTTP methods:

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
      methods=("GET", "HEAD", "OPTIONS", "TRACE"),
   )

When enabled, :class:`RetryMiddleware <aioscraper.middlewares.retry.RetryMiddleware>` is registered automatically as the innermost middleware (closest to dispatch) and reschedules the request through the internal queue.

.. _retry-idempotency:

Idempotency
~~~~~~~~~~~

A retry replays the whole request. If the server already applied it and only the response was lost, a
replayed ``POST``/``PATCH`` is a second charge, a duplicate entity or a duplicate row. ``methods``
therefore lists only the idempotent methods by default — ``GET``, ``HEAD``, ``OPTIONS``, ``TRACE`` — and
requests using any other method are never retried, whatever the status or exception says. Method matching
is case-insensitive.

``PUT`` and ``DELETE`` are idempotent per RFC 9110, but only if the endpoint implements them that way, so
they are opt-in:

.. code-block:: python

   from aioscraper.config import RequestRetryConfig

   retry_config = RequestRetryConfig(enabled=True, methods=("GET", "HEAD", "PUT", "DELETE"))

:attr:`Request.retryable <aioscraper.types.session.Request.retryable>` overrides the method check for a
single request — ``True`` retries it, ``False`` never does, ``None`` (the default) defers to ``methods``:

.. code-block:: python

   from uuid import uuid4

   from aioscraper.types import Request, SendRequest


   async def scraper(send_request: SendRequest):
       # safe to replay: the server deduplicates by Idempotency-Key
       await send_request(
           Request(
               url="https://api.example.com/payments",
               method="POST",
               json_data={"amount": 100},
               headers={"Idempotency-Key": str(uuid4())},
               retryable=True,
           ),
       )

Generating the idempotency key and choosing its scope are the application's job: aioscraper replays the
request object as it is, headers and body included.

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

.. autoclass:: aioscraper.config.models.SchedulerConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.models.ExecutionConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.models.PipelineConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.models.RequestRetryConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.models.RateLimitConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.models.AdaptiveRateLimitConfig
   :members:
   :no-index: