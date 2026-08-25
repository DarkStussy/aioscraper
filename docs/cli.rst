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

.. _cli-entrypoint-timing:

Instance or factory
~~~~~~~~~~~~~~~~~~~

The two forms differ in *when* the scraper is built. A module-level instance is built while the CLI
imports the module, so its configuration is resolved at import time; a factory runs afterwards, once
the arguments are parsed.

That is what makes the factory the place for a configuration loader of your own:

.. code-block:: python

   from aioscraper import AIOScraper


   def make() -> AIOScraper:
       return AIOScraper(scrape, config=load_my_config())

``examples/third_party_config.py`` is a runnable version.

Running without the CLI
-----------------------

You can run the same scraper programmatically using :func:`run_scraper <aioscraper.core.runner.run_scraper>`:

.. code-block:: python

    import asyncio
    from aioscraper import AIOScraper, Request, ScheduleRequest, run_scraper
    from aioscraper.config import load_config


    async def scrape(schedule_request: ScheduleRequest):
        await schedule_request(Request(url="https://example.com"))


    async def main() -> int:
        scraper = AIOScraper(scrape, config=load_config())
        result = await run_scraper(scraper)
        if result.interrupted:
            return 130

        return 0 if result.ok else 1


    if __name__ == "__main__":
        raise SystemExit(asyncio.run(main()))


This gives you the same signal handling and graceful shutdown behavior as the CLI.
``run_scraper`` expects ``scraper.config`` to be set ahead of time, which is why the example passes ``config=load_config()`` to the constructor.

:func:`run_scraper <aioscraper.core.runner.run_scraper>` returns a :class:`RunResult <aioscraper.core.errors.RunResult>` and never acts on it: turning the outcome into an exit code is the caller's decision, and the CLI is one implementation of it. The handlers turn SIGINT/SIGTERM into an event, so ``KeyboardInterrupt`` never reaches the caller — ``result.interrupted`` is how a signalled run is told apart from a clean one.

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
- ``--allow-partial-success``: Exit ``0`` even when the run recorded unhandled errors (overrides ``EXECUTION_ON_ERROR``, see :ref:`unhandled errors <unhandled-errors>`).

Exit codes
~~~~~~~~~~

- ``0`` - the run finished, with nothing recorded or with errors the policy waives.
- ``1`` - the run finished but recorded unhandled errors under ``ErrorPolicy.FAIL`` (the default).
- ``124`` - ``execution.timeout`` expired, so the run never finished. Not waivable by the policy or the flag.
- ``130`` - SIGINT/SIGTERM stopped the run. Takes precedence over the rest.

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
- ``SESSION_MAX_RESPONSE_BODY_SIZE`` → ``max_response_body_size``; ``0``, ``none`` or ``unlimited`` turns the cap off (:ref:`docs <body-limits>`)
- ``SESSION_MAX_ERROR_BODY_SIZE`` → ``max_error_body_size`` (:ref:`docs <body-limits>`)
- ``SESSION_BUFFER_BODY`` → ``buffer_body`` (:ref:`docs <body-buffering>`)

:class:`RequestRetryConfig <aioscraper.config.models.RequestRetryConfig>`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Retry behavior (:ref:`docs <retry-config>`).

- ``SESSION_RETRY_ENABLED`` → ``enabled``
- ``SESSION_RETRY_ATTEMPTS`` → ``attempts``
- ``SESSION_RETRY_BACKOFF`` → ``backoff``
- ``SESSION_RETRY_BASE_DELAY`` → ``base_delay``
- ``SESSION_RETRY_MAX_DELAY`` → ``max_delay``
- ``SESSION_RETRY_MAX_RETRY_AFTER`` → ``max_retry_after``
- ``SESSION_RETRY_STATUSES`` → ``statuses``
- ``SESSION_RETRY_EXCEPTIONS`` → ``exceptions``
- ``SESSION_RETRY_METHODS`` → ``methods``

:class:`RateLimitConfig <aioscraper.config.models.RateLimitConfig>`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Rate limiting behavior (:ref:`docs <rate-limit-config>`).

``SESSION_RATE_LIMIT_GROUP_CONCURRENCY`` needs ``SESSION_RATE_LIMIT_PER_GROUP=true`` as well, since
it limits one group at a time; without it :func:`load_config <aioscraper.config.loader.load_config>`
raises :class:`ConfigValidationError <aioscraper.exceptions.ConfigValidationError>`.

- ``SESSION_RATE_LIMIT_PER_GROUP`` → ``per_group``
- ``SESSION_RATE_LIMIT_INTERVAL`` → ``default_interval``
- ``SESSION_RATE_LIMIT_CLEANUP_TIMEOUT`` → ``cleanup_timeout``
- ``SESSION_RATE_LIMIT_GROUP_CONCURRENCY`` → ``group_concurrency``

:class:`AdaptiveRateLimitConfig <aioscraper.config.models.AdaptiveRateLimitConfig>`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Adaptive rate limiting (EWMA + AIMD) (:ref:`docs <adaptive-rate-limiting>`).

Set ``SESSION_RATE_LIMIT_ADAPTIVE_ENABLED=true`` to enable and configure other parameters. It needs
``SESSION_RATE_LIMIT_PER_GROUP=true`` as well, since adaptive paces a group at a time; without it
:func:`load_config <aioscraper.config.loader.load_config>` raises
:class:`ConfigValidationError <aioscraper.exceptions.ConfigValidationError>`.

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
- ``SCHEDULER_READY_QUEUE_MAX_SIZE`` → ``ready_queue_max_size`` (throttles the scraper entrypoint; not a hard cap)

:class:`ExecutionConfig <aioscraper.config.models.ExecutionConfig>`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Execution and shutdown behavior.

- ``EXECUTION_TIMEOUT`` → ``timeout``
- ``EXECUTION_SHUTDOWN_TIMEOUT`` → ``shutdown_timeout``
- ``EXECUTION_SHUTDOWN_CHECK_INTERVAL`` → ``shutdown_check_interval``
- ``EXECUTION_ON_ERROR`` → ``on_error`` (``fail`` or ``log``)
- ``EXECUTION_MAX_RETAINED_ERRORS`` → ``max_retained_errors`` (:ref:`docs <unhandled-errors>`)
- ``EXECUTION_LOG_LEVEL`` → ``log_level``

:class:`PipelineConfig <aioscraper.config.models.PipelineConfig>`
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Pipeline dispatching behavior.

- ``PIPELINE_STRICT`` → ``strict``
