Configuration
=============

Everything a run is configured with lives in four groups: the HTTP session, the scheduler, execution and shutdown, and pipeline dispatching. The defaults are usable as they are; the settings below are the ones worth revisiting for a real target.

You can build a :class:`Config <aioscraper.config.models.Config>` and pass it to :class:`AIOScraper <aioscraper.core.scraper.AIOScraper>` via ``AIOScraper(config=...)``, or override values via :ref:`environment variables <cli-configuration>`.
The CLI reads well-known environment variables (for example ``SESSION_REQUEST_TIMEOUT``, ``SCHEDULER_CONCURRENT_REQUESTS``, ``EXECUTION_TIMEOUT``, ``PIPELINE_STRICT``) and applies them before launching the scraper.

The HTTP client is chosen at runtime: ``aiohttp`` is used when installed, then ``httpx``, then ``httpx2``. Install one of the extras from :doc:`/installation` so requests can be executed.
Set :class:`SessionConfig.http_backend <aioscraper.config.models.SessionConfig>` (or ``SESSION_HTTP_BACKEND``) to a value from :class:`HttpBackend <aioscraper.config.models.HttpBackend>` if you want to force one client even when several are available.


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

.. _config-hooks:

Hooks are not configuration
---------------------------

``Config`` holds only what a file or an environment variable can hold. The two settings that are code
- ``group_by`` and ``should_retry`` - are arguments of :class:`AIOScraper <aioscraper.core.scraper.AIOScraper>`,
next to ``http_client`` and ``sessionmaker_factory``:

.. code-block:: python

    scraper = AIOScraper(config=config, group_by=custom_group_by, should_retry=should_retry)

Both are also plain attributes, so a test or a lifespan can replace them until the run starts.

That split is what lets any loader that fills dataclasses from their annotations build the whole
``Config``. Three fields name their object indirectly: ``session.ssl`` takes a path to a CA bundle,
``retry.exceptions`` and ``adaptive.custom_trigger_exceptions`` take dotted paths. A loader resolves
them with :func:`parse_ssl <aioscraper.config.converters.parse_ssl>` and :func:`parse_exception
<aioscraper.config.converters.parse_exception>`, which raise ``ValueError`` on anything they cannot
resolve, with the underlying failure chained.

:func:`load_config <aioscraper.config.loader.load_config>` reads the environment through the same two
functions, so a file and a variable resolve identically. ``examples/third_party_config.py`` wires
this up end to end. Under the CLI, build it in a :ref:`factory entrypoint <cli-entrypoint-timing>`:
a module-level ``AIOScraper()`` resolves its configuration while the module is being imported.

Graceful shutdown
-----------------

- ``execution.timeout`` - overall budget (``None`` by default, i.e. no total limit); on expiry the runner logs at ``execution.log_level`` and cancels all tasks.
- ``execution.shutdown_timeout`` - grace period after SIGINT/SIGTERM/timeout before in-flight work is canceled outright.
- ``execution.shutdown_check_interval`` - pause between drain checks while waiting for the scheduler/queue to empty.
- Signals: first SIGINT/SIGTERM initiates shutdown, second triggers force-exit. Lifespan is shielded so cleanup still runs.

.. _unhandled-errors:

Unhandled errors
----------------

A request that fails without an ``errback``, a failing ``errback``, and a resource that will not close are
logged and then dropped so the rest of the run continues. A failure handled by your own ``errback`` is
not recorded: handling it is the point of the callback.

:meth:`wait() <aioscraper.core.scraper.AIOScraper.wait>`,
:meth:`shutdown() <aioscraper.core.scraper.AIOScraper.shutdown>` and
:func:`run_scraper <aioscraper.core.runner.run_scraper>` return a
:class:`RunResult <aioscraper.core.errors.RunResult>` describing the outcome:

- ``error_counts`` - exact totals per context, and ``total_errors`` across all of them.
- ``errors`` - the most recent exceptions, capped by ``execution.max_retained_errors``
  (``EXECUTION_MAX_RETAINED_ERRORS``, 100 by default) so a run failing millions of requests does not keep
  every traceback alive. ``0`` keeps none; the counts stay exact either way.
- ``interrupted`` / ``timed_out`` - whether a signal or ``execution.timeout`` ended the run.
- ``ok`` - true only when the run finished on its own with nothing recorded. A failure your ``errback``
  handled is not recorded, so it leaves ``ok`` true.
- ``all_requests_succeeded`` - true when no request ended in failure, handled or not. It follows
  ``requests_failed``, so a failure a retry recovered from does not count, and work the run never
  attempted is not covered - that is what ``interrupted`` and ``timed_out`` are for.
- ``requests_started`` / ``requests_succeeded`` / ``requests_failed`` - attempts rather than requests: a
  retry starts another one, and only the attempt that ends a request counts as succeeded or failed.
  ``requests_failed`` covers failures an ``errback`` handled, which ``error_counts`` deliberately leaves out.
- ``requests_retried`` - attempts the retry policy admitted again, which end neither as succeeded nor
  as failed.
- ``items_processed`` - items the pipeline dispatcher handled without raising.

The same data stays available on the scraper through
:attr:`AIOScraper.result <aioscraper.core.scraper.AIOScraper.result>`, and the errors alone through
:attr:`AIOScraper.error_counts <aioscraper.core.scraper.AIOScraper.error_counts>` and
:attr:`AIOScraper.errors <aioscraper.core.scraper.AIOScraper.errors>`.

``execution.on_error`` is applied by the **CLI only**, as an exit code:

- ``ErrorPolicy.FAIL`` (default) - exit ``1`` when anything was recorded.
- ``ErrorPolicy.LOG`` - exit ``0`` regardless.

The default is ``FAIL`` because the alternative reports a scheduled job that lost part of its data as a
success to cron, CI or Kubernetes. Where partial results really are acceptable, say so explicitly - with
``EXECUTION_ON_ERROR=log`` or the ``--allow-partial-success`` flag, which overrides the config.

Neither waives an unfinished run: SIGINT/SIGTERM exits ``130`` and an expired ``execution.timeout`` exits
``124``, whatever the policy says. They apply to errors that were recorded, while a run cut short left work
it never attempted.

:func:`run_scraper <aioscraper.core.runner.run_scraper>` itself acts on neither the policy nor the flag: it
reports the outcome and leaves the decision to the caller.

The shutdown settings above are honored by both the CLI and ``run_scraper``, giving consistent stop behavior in
code or from the terminal.


.. _own-http-client:

Bringing your own HTTP client
-----------------------------

Pass an ``aiohttp.ClientSession``, an ``httpx.AsyncClient`` or an ``httpx2.AsyncClient`` as ``AIOScraper(http_client=...)`` to send through a client your service already owns, with its connection pool, default headers, cookies, auth and transports:

.. code-block:: python

    from aiohttp import ClientSession
    from aioscraper import AIOScraper


    async def main(http_client: ClientSession):
        scraper = AIOScraper(http_client=http_client)
        ...

The client picks the backend, so ``session.http_backend`` only has to agree with it; a mismatch raises :class:`AIOScraperException <aioscraper.exceptions.AIOScraperException>`.

The contract for a client passed this way:

- It is used as configured. ``session.timeout``, ``ssl`` and ``proxy`` build a client `aioscraper` creates, so they no longer apply - set the equivalents on the client itself. The same goes for httpx's redirect limit, which `aioscraper` otherwise pins to ``Request.max_redirects``.
- It stays open. The scraper never closes a client it did not create, so one client can outlive many runs.
- What the framework enforces itself is unaffected: :ref:`body limits <body-limits>`, :ref:`retries <retry-config>`, :ref:`rate limiting <rate-limit-config>`, and per-request fields such as ``Request.timeout`` or ``Request.headers``, which the client merges with its own defaults.
- The connection pool stays the client's. ``scheduler.concurrent_requests`` bounds requests in flight, but the pool serving them is sized on the client.

:func:`get_sessionmaker <aioscraper.core.session.factory.get_sessionmaker>` takes the same ``client`` argument, and :class:`AiohttpSession <aioscraper.core.session.aiohttp.AiohttpSession>`/:class:`HttpxSession <aioscraper.core.session.httpx.HttpxSession>` accept ``client=`` with ``owns_client=`` to hand ownership over explicitly. ``http_client`` and ``sessionmaker_factory`` are mutually exclusive: a custom factory decides on its own client.

.. _body-limits:

Body limits
-----------

Two independent caps bound how much of a response ends up in memory:

- ``max_response_body_size`` (``SESSION_MAX_RESPONSE_BODY_SIZE``) applies to bodies handed to callbacks,
  through both :meth:`read() <aioscraper.types.session.Response.read>` and :meth:`iter_bytes()
  <aioscraper.types.session.Response.iter_bytes>`. It raises :class:`ResponseTooLarge
  <aioscraper.exceptions.ResponseTooLarge>` at the chunk that crosses it, so the rest is never pulled from
  the socket. Defaults to 32 MiB; ``None`` (``SESSION_MAX_RESPONSE_BODY_SIZE=0``) disables it.
- ``max_error_body_size`` (``SESSION_MAX_ERROR_BODY_SIZE``) applies to a failed response, whose body is read
  only to fill the :class:`HTTPException <aioscraper.exceptions.HTTPException>` message. Defaults to 64 KiB;
  a longer body is cut at the limit and the message ends with ``[truncated]``. ``0`` skips reading it.

.. code-block:: python

    from aioscraper.config import SessionConfig

    session_config = SessionConfig(
        max_response_body_size=32 * 1024 * 1024,
        max_error_body_size=8 * 1024,
    )

Both are on by default: a run holds ``scheduler.concurrent_requests`` bodies at once, so the response cap
bounds that product - 2 GiB with the defaults. Raise it for large downloads. The error cap is separate
because an endpoint answering ``500`` with gigabytes of HTML would otherwise be buffered whole for an
error message.

That product is what a run holds, not what it peaks at. Assembling a body into ``bytes`` needs about twice
its size while the copy is made, and :meth:`text() <aioscraper.types.session.Response.text>` and
:meth:`json() <aioscraper.types.session.Response.json>` hold the decoded string alongside it. Size a
memory limit above the product, or stream with :meth:`iter_bytes()
<aioscraper.types.session.Response.iter_bytes>`, which buffers nothing.

.. _body-buffering:

Body buffering
--------------

A response reaches its callback with the body still on the socket, so a connection that dies mid-body
fails inside the callback - past the retry policy, which ends when the handler returns. The failure
reaches the errback unretried, and the adaptive rate limiter has already recorded the request as a
success at the latency of its headers.

``buffer_body`` (``SESSION_BUFFER_BODY``) reads the body first, moving both inside the request: the read
is retried like any other transport failure, and the recorded latency covers the whole response.

.. code-block:: python

    from aioscraper import Request

    request = Request("https://api.example.com/data", buffer_body=True)

:meth:`read() <aioscraper.types.session.Response.read>` and :meth:`iter_bytes()
<aioscraper.types.session.Response.iter_bytes>` replay the buffer, and ``max_response_body_size`` still
applies. It is off by default: a buffered body stays in memory for the whole callback, which a callback
streaming a large download to disk does not want.

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

A group paces its requests; it does not get a share of the concurrency. ``scheduler.concurrent_requests`` is a single global limit, so requests waiting on a slow host hold slots that every other group would otherwise use. Size the limit for the slowest target, or run a scraper per target, to keep them apart.

.. code-block:: python

   from aioscraper.config import RateLimitConfig

   rate_limit_config = RateLimitConfig(
       per_group=True,
       default_interval=0.5,  # 500ms between requests per host
       cleanup_timeout=60.0,  # Clean up idle groups after 60 seconds
   )

**Configuration options:**

- ``per_group``: Pace each group separately rather than the run as a whole (default: ``False``).
- ``default_interval``: Delay in seconds between requests - within each group, or across the whole run when ``per_group`` is off (default: ``0.0``).
- ``cleanup_timeout``: Timeout in seconds for cleaning up inactive request groups (default: ``60.0``).
- ``adaptive``: Enable :ref:`adaptive rate limiting <adaptive-rate-limiting>` (default: ``None``). Requires ``per_group``.

``per_group`` is not an on/off switch: ``default_interval`` applies either way, as one delay for the
whole run or as one per group.


Custom grouping
~~~~~~~~~~~~~~~

``group_by`` maps a request to its group key and that group's interval, so different domains or
endpoints can be paced differently. It is code rather than configuration, so it goes to
:class:`AIOScraper <aioscraper.core.scraper.AIOScraper>` and not to ``RateLimitConfig`` - see
:ref:`hooks <config-hooks>`:

.. code-block:: python

   from yarl import URL
   from aioscraper import AIOScraper
   from aioscraper.config import Config, RateLimitConfig, SessionConfig


   def custom_group_by(request):
      """Group by domain with custom intervals."""
      host = URL(request.url).host
      if host == "api.example.com":
         return (host, 0.1)  # 100ms for API
      elif host == "www.example.com":
         return (host, 1.0)  # 1 second for website

      return (host, 0.5)  # 500ms default


   scraper = AIOScraper(
       config=Config(session=SessionConfig(rate_limit=RateLimitConfig(per_group=True))),
       group_by=custom_group_by,
   )

When ``per_group=False`` (default), ``group_by`` is not consulted and ``default_interval`` becomes a single delay between all requests.

.. _adaptive-rate-limiting:

Adaptive Rate Limiting
~~~~~~~~~~~~~~~~~~~~~~~

Adaptive rate limiting lets each group find its own pace instead of holding the one you configured, on the **AIMD (Additive Increase Multiplicative Decrease)** pattern TCP congestion control uses. **EWMA (Exponentially Weighted Moving Average)** smooths the latency it tracks alongside.

How it works:

- Pushback (429, 503, timeouts) multiplies the interval at once - one bad response is enough to back off
- A run of successes takes a small step off it - capacity is reclaimed slowly, and given up quickly
- A ``Retry-After`` overrides both: what the server asked for beats anything inferred
- Every group adapts on its own history, so a slow host does not throttle a fast one

.. code-block:: python

   from aioscraper.config import RateLimitConfig, AdaptiveRateLimitConfig

   rate_limit_config = RateLimitConfig(
       per_group=True,  # required: adaptive paces a group at a time
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

**Integration with retries:**

When both adaptive rate limiting and :ref:`retries <retry-config>` are enabled:

- **Retries** handle the repeat itself (attempts, backoff)
- **Adaptive rate limiter** adjusts the *sending rate* to prevent future failures
- Trigger statuses/exceptions are shared when ``inherit_retry_triggers=True``

This prevents the system from repeatedly hammering an overloaded server while retries are ongoing.

.. _retry-config:

Retries
-------

Retries are on by default. A failing endpoint therefore costs ``attempts`` extra requests per URL and the
run takes the backoff delays; ``SESSION_RETRY_ENABLED=false`` or
:class:`RequestRetryConfig(enabled=False) <aioscraper.config.models.RequestRetryConfig>` turns them off.
Only idempotent methods are replayed - see :ref:`idempotency <retry-idempotency>`.

Retries are applied by the dispatcher, not by a middleware: a matching failure is admitted to the internal
queue again with the computed delay, and neither the callback nor the errback fires for that attempt. The
decision sits around the whole :doc:`middleware chain <middlewares>`, so a failure a middleware raised
itself is judged too, while the callback stays outside it — failing to process a response is no reason to
fetch it again.

The retry count belongs to the attempt, not to the request object, so sending one ``Request`` twice gives
each send its own budget, and a request reused in a later run starts from zero.

.. code-block:: python

   from aioscraper.config import RequestRetryConfig, BackoffStrategy
   from aioscraper.exceptions import ConnectionFailed, TransportTimeout

   retry_config = RequestRetryConfig(
      enabled=True,
      attempts=5,
      backoff=BackoffStrategy.EXPONENTIAL_JITTER,
      base_delay=1.0,
      max_delay=5.0,
      statuses=(500, 502, 503),
      exceptions=(TransportTimeout, ConnectionFailed),
      methods=("GET", "HEAD", "OPTIONS", "TRACE"),
   )

``exceptions`` defaults to those two, the transient half of the :ref:`transport hierarchy
<transport-errors>`: a timeout, and a connection that could not be made or was lost - DNS and proxy
failures included, as :class:`ConnectionFailed <aioscraper.exceptions.ConnectionFailed>`. They mean the
same thing on every backend, so one policy covers all three.
:class:`TLSError <aioscraper.exceptions.TLSError>` is left out: a certificate or protocol mismatch fails
again on the next attempt. Add it, or the client's own classes, to retry more.

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

``should_retry`` covers failures ``statuses``/``exceptions`` cannot express — a marker in the error body,
or an error code inside a ``200`` that your own middleware turns into an exception. Like ``group_by`` it
is a :ref:`hook <config-hooks>` on the scraper, not a config field:

.. code-block:: python

   from aioscraper import AIOScraper
   from aioscraper.exceptions import HTTPException
   from aioscraper.types import Request


   def should_retry(request: Request, exc: Exception, retries: int) -> bool | None:
       if isinstance(exc, HTTPException) and "rate limit" in exc.message:
           return True

       return None  # fall back to the statuses/exceptions match


   scraper = AIOScraper(should_retry=should_retry)

``True``/``False`` is final; ``None`` defers to ``statuses``/``exceptions``. The method check below runs
before the hook either way, so a hook cannot widen retries to a non-idempotent request.

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

   from aioscraper.types import Request, ScheduleRequest


   async def scraper(schedule_request: ScheduleRequest):
       # safe to replay: the server deduplicates by Idempotency-Key
       await schedule_request(
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

A ``Retry-After`` header (RFC 9110) on a ``429 Too Many Requests`` or ``503 Service Unavailable`` replaces the computed backoff for that attempt: the server knows when it will be ready and the backoff curve does not. It is read on those two statuses only.

The ``Retry-After`` header can be specified as:

- **Seconds**: ``Retry-After: 120`` (wait 120 seconds)
- **HTTP-date**: ``Retry-After: Wed, 21 Oct 2015 07:28:00 GMT``

A longer delay than ``max_retry_after`` (``SESSION_RETRY_MAX_RETRY_AFTER``, 600 seconds by default) is
clamped to it. Since retries are on by default, that cap is what stops a server from parking a run for as
long as it likes: lower it where a job has a deadline, and remember that a parked request keeps the run
alive until it is sent.


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