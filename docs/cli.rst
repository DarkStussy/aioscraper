CLI
==========

Run scrapers from the command line without wiring up the event loop yourself.


.. code-block:: bash

   pip install aioscraper
   aioscraper scraper

See the minimal code in :doc:`/quickstart`.

Entrypoint contract
-------------------

The CLI loads a module (file path or ``module.path``) and optionally a specific attribute using ``module:attr``.

Entry rules:

- Without ``:attr``: the CLI looks for a ``scraper`` attribute that is either an :class:`AIOScraper <aioscraper.core.scraper.AIOScraper>` instance or a callable returning one.
- With ``:attr`` pointing to an :class:`AIOScraper <aioscraper.core.scraper.AIOScraper>`: the CLI uses that instance.
- With ``:attr`` pointing to a callable (sync **or async**): the CLI executes/awaits it and expects an :class:`AIOScraper <aioscraper.core.scraper.AIOScraper>` instance in return.

Examples
~~~~~~~~

.. code-block:: bash

   aioscraper scraper                   # uses scraper variable from scraper.py
   aioscraper mypkg.scraper:custom_app  # uses custom_app AIOScraper instance
   aioscraper mypkg.factory:make        # calls make() (sync factory)
   aioscraper mypkg.factory:make_async  # awaits make_async() (async factory)

For resource setup/teardown around the same scraper instance, attach a ``lifespan(scraper)`` when constructing the scraper in code (see :doc:`/concepts/lifespan`).

Running without the CLI
-----------------------

You can run the same scraper programmatically using :func:`run_scraper <aioscraper.core.runner.run_scraper>`:

.. code-block:: python

    import asyncio
    from aioscraper import AIOScraper, Request, SendRequest, run_scraper
    from aioscraper.config import load_config


    async def scrape(send_request: SendRequest):
        await send_request(Request(url="https://example.com"))


    async def main():
        scraper = AIOScraper(scrape, config=load_config())
        await run_scraper(scraper)


    if __name__ == "__main__":
        asyncio.run(main())


This gives you the same signal handling and graceful shutdown behavior as the CLI.
``run_scraper`` expects ``scraper.config`` to be set ahead of time, which is why the example passes ``config=load_config()`` to the constructor.

.. _cli-configuration:

Configuration
-------------

Configuration precedence (when the CLI needs to load a config): CLI flags -> environment variables -> :class:`Config <aioscraper.config.models.Config>` defaults.
If the resolved :class:`AIOScraper <aioscraper.core.scraper.AIOScraper>` already has ``config`` set, the CLI leaves it untouched and CLI flags/env vars are ignored.

See :doc:`/concepts/config` for detailed configuration options and examples.

CLI flags
~~~~~~~~~

- ``--concurrent-requests``: Max concurrent requests (overrides ``SCHEDULER_CONCURRENT_REQUESTS``).
- ``--pending-requests``: Pending requests to keep queued (overrides ``SCHEDULER_PENDING_REQUESTS``).

Environment variables
~~~~~~~~~~~~~~~~~~~~~

All environment variables map directly to fields in :class:`Config <aioscraper.config.models.Config>` and its nested configuration classes.
The CLI reads these variables automatically. For programmatic use, call :func:`load_config <aioscraper.config.loader.load_config>` to read environment variables and construct a ``Config`` instance.

:class:`SessionConfig <aioscraper.config.models.SessionConfig>`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

HTTP session and client behavior.

- ``SESSION_REQUEST_TIMEOUT`` → ``timeout``
- ``SESSION_SSL`` → ``ssl``
- ``SESSION_PROXY`` → ``proxy`` (:ref:`docs <proxy-config>`)
- ``SESSION_HTTP_BACKEND`` → ``http_backend``

:class:`RequestRetryConfig <aioscraper.config.models.RequestRetryConfig>`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Retry middleware behavior (:ref:`docs <retry-config>`).

- ``SESSION_RETRY_ENABLED`` → ``enabled``
- ``SESSION_RETRY_ATTEMPTS`` → ``attempts``
- ``SESSION_RETRY_BACKOFF`` → ``backoff``
- ``SESSION_RETRY_BASE_DELAY`` → ``base_delay``
- ``SESSION_RETRY_MAX_DELAY`` → ``max_delay``
- ``SESSION_RETRY_STATUSES`` → ``statuses``
- ``SESSION_RETRY_EXCEPTIONS`` → ``exceptions``
- ``SESSION_RETRY_MIDDLEWARE_PRIORITY`` → ``middleware.priority``
- ``SESSION_RETRY_MIDDLEWARE_STOP`` → ``middleware.stop_processing``

:class:`RateLimitConfig <aioscraper.config.models.RateLimitConfig>`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Rate limiting behavior (:ref:`docs <rate-limit-config>`).

- ``SESSION_RATE_LIMIT_ENABLED`` → ``enabled``
- ``SESSION_RATE_LIMIT_INTERVAL`` → ``default_interval``
- ``SESSION_RATE_LIMIT_CLEANUP_TIMEOUT`` → ``cleanup_timeout``

:class:`AdaptiveRateLimitConfig <aioscraper.config.models.AdaptiveRateLimitConfig>`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Adaptive rate limiting (EWMA + AIMD) (:ref:`docs <adaptive-rate-limiting>`).

Set ``SESSION_RATE_LIMIT_ADAPTIVE_ENABLED=true`` to enable and configure other parameters.

- ``SESSION_RATE_LIMIT_ADAPTIVE_MIN_INTERVAL`` → ``min_interval``
- ``SESSION_RATE_LIMIT_ADAPTIVE_MAX_INTERVAL`` → ``max_interval``
- ``SESSION_RATE_LIMIT_ADAPTIVE_INCREASE_FACTOR`` → ``increase_factor``
- ``SESSION_RATE_LIMIT_ADAPTIVE_DECREASE_STEP`` → ``decrease_step``
- ``SESSION_RATE_LIMIT_ADAPTIVE_SUCCESS_THRESHOLD`` → ``success_threshold``
- ``SESSION_RATE_LIMIT_ADAPTIVE_EWMA_ALPHA`` → ``ewma_alpha``
- ``SESSION_RATE_LIMIT_ADAPTIVE_RESPECT_RETRY_AFTER`` → ``respect_retry_after``
- ``SESSION_RATE_LIMIT_ADAPTIVE_INHERIT_RETRY_TRIGGERS`` → ``inherit_retry_triggers``

:class:`SchedulerConfig <aioscraper.config.models.SchedulerConfig>`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Request scheduler behavior.

- ``SCHEDULER_CONCURRENT_REQUESTS`` → ``concurrent_requests``
- ``SCHEDULER_PENDING_REQUESTS`` → ``pending_requests``
- ``SCHEDULER_CLOSE_TIMEOUT`` → ``close_timeout``
- ``SCHEDULER_READY_QUEUE_MAX_SIZE`` → ``ready_queue_max_size``

:class:`ExecutionConfig <aioscraper.config.models.ExecutionConfig>`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Execution and shutdown behavior.

- ``EXECUTION_TIMEOUT`` → ``timeout``
- ``EXECUTION_SHUTDOWN_TIMEOUT`` → ``shutdown_timeout``
- ``EXECUTION_SHUTDOWN_CHECK_INTERVAL`` → ``shutdown_check_interval``
- ``EXECUTION_LOG_LEVEL`` → ``log_level``

:class:`PipelineConfig <aioscraper.config.models.PipelineConfig>`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pipeline dispatching behavior.

- ``PIPELINE_STRICT`` → ``strict``
