Configuration
=============

`aioscraper` ships sane defaults but exposes configuration for sessions, scheduling, execution, and pipeline dispatching.

You can build a :class:`Config <aioscraper.config.Config>` and pass it to :class:`AIOScraper <aioscraper.core.scraper.AIOScraper>` via ``AIOScraper(config=...)``, or override values via :ref:`environment variables <cli-configuration>`. 
The CLI reads well-known environment variables (for example ``SESSION_REQUEST_TIMEOUT``, ``SCHEDULER_CONCURRENT_REQUESTS``, ``EXECUTION_TIMEOUT``, ``PIPELINE_STRICT``) and applies them before launching the scraper.

The HTTP client is chosen at runtime: ``aiohttp`` is used when installed, otherwise ``httpx``. Install one of the extras from :doc:`/installation` so requests can be executed. 
Set ``session.http_backend`` (or ``SESSION_HTTP_BACKEND``) to a value from :class:`HttpBackend <aioscraper.config.HttpBackend>` if you want to force one client even when both are available. 


.. code-block:: python

    import logging
    from aioscraper import AIOScraper, run_scraper
    from aioscraper.config import Config, SessionConfig, SchedulerConfig, ExecutionConfig, PipelineConfig

    config = Config(
        session=SessionConfig(timeout=20, delay=0.05, ssl=True, proxy="http://localhost:8080"),
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

``SessionConfig.proxy`` (and ``SESSION_PROXY``) accepts two shapes; pick the one your HTTP client supports:

- ``aiohttp`` — ``"http://user:pass@127.0.0.1:8080"`` (single proxy applied to every request).
- ``httpx`` (single proxy) — ``"http://socks5://localhost:9050"`` when one proxy handles all schemes.
- ``httpx`` (per-scheme) — ``{"http": "http://corp-proxy:8080", "https": "http://secure-proxy:8443"}`` to route ``http``/``https`` separately.

.. warning::

   ``httpx`` only supports client-scoped proxies, so per-request overrides are ignored. ``aiohttp`` does the opposite: a proxy passed directly in ``Request(..., proxy=...)`` takes precedence over ``config.session.proxy``.

.. _retry-config:

Retries
-------

Set ``SessionConfig.retry`` or override values via :ref:`environment variables <cli-configuration>` to enable the built-in retry middleware.

You can pick the number of retry attempts, status codes, exception types:

.. code-block:: python

    import asyncio
    from aioscraper.config import SessionConfig, RequestRetryConfig

    session = SessionConfig(
        retry=RequestRetryConfig(
            enabled=True,
            attempts=2,
            delay=1,
            statuses=(500, 502, 503),
            exceptions=(asyncio.TimeoutError,),
        )
    )

When enabled, :class:`RetryMiddleware <aioscraper.middlewares.retry.RetryMiddleware>` is registered automatically as an exception middleware and reschedules the request through the internal queue. 
You can override its priority/``stop_processing`` behaviour via ``RequestRetryConfig.middleware``.


.. autoclass:: aioscraper.config.Config
   :members:
   :no-index:

.. autoclass:: aioscraper.config.SessionConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.RequestRetryConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.SchedulerConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.ExecutionConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.PipelineConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.MiddlewareConfig
   :members:
   :no-index: