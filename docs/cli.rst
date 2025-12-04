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

- Without ``:attr``: the CLI looks for a ``scraper`` attribute that is an :class:`AIOScraper <aioscraper.scraper.core.AIOScraper>` instance. If the module also exposes ``lifespan(scraper)``, the CLI will wrap the scraper with it before starting.
- With ``:attr`` pointing to an :class:`AIOScraper <aioscraper.scraper.core.AIOScraper>`: the CLI uses that instance. If the module exposes ``lifespan``, it will wrap the scraper with it.
- With ``:attr`` equal to ``lifespan``: the CLI creates a new :class:`AIOScraper <aioscraper.scraper.core.AIOScraper>` and passes it into that context manager; register scrapers inside the lifespan.

Examples:

.. code-block:: bash

   aioscraper scraper                   # uses scraper variable from scraper.py
   aioscraper mypkg.scraper:custom_app  # uses custom_app AIOScraper instance
   aioscraper mypkg.setup:lifespan      # uses lifespan(scraper) context manager

For resource setup/teardown around the same scraper instance, provide a ``lifespan(scraper)`` async context manager (see :doc:`/concepts/lifespan`).

Configuration
-------------

Configuration precedence: CLI flags -> environment variables -> :class:`Config <aioscraper.config.Config>` defaults.

- ``--concurrent-requests``: Max concurrent requests (overrides ``SCHEDULER_CONCURRENT_REQUESTS``).
- ``--pending-requests``: Pending requests to keep queued (overrides ``SCHEDULER_PENDING_REQUESTS``).

Supported environment variables:

- ``SESSION_REQUEST_TIMEOUT``: Request timeout (seconds).
- ``SESSION_REQUEST_DELAY``: Delay between requests (seconds).
- ``SESSION_SSL``: Enable/disable SSL.
- ``SCHEDULER_CONCURRENT_REQUESTS``: Max concurrent requests.
- ``SCHEDULER_PENDING_REQUESTS``: Pending requests to maintain.
- ``SCHEDULER_CLOSE_TIMEOUT``: Scheduler shutdown timeout (seconds).
- ``EXECUTION_TIMEOUT``: Global execution timeout (seconds).
- ``EXECUTION_SHUTDOWN_TIMEOUT``: Graceful shutdown timeout (seconds).
- ``EXECUTION_SHUTDOWN_CHECK_INTERVAL``: Interval between shutdown checks (seconds).
- ``EXECUTION_LOG_LEVEL``: Log level name used when timeouts occur (e.g., ``WARNING``, ``ERROR``).
- ``PIPELINE_STRICT``: Whether to raise when an item references a missing pipeline.
