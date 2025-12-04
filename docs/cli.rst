CLI
==========

Run scrapers from the command line without wiring up the event loop yourself.


.. code-block:: bash

   pip install aioscraper
   aioscraper scraper

Entrypoint contract
-------------------

The CLI loads a module or file that exposes an async context manager named ``lifespan`` by default. It receives the pre-built :class:`aioscraper.AIOScraper` instance so you can register scrapers, pipelines, and middlewares before execution starts.

Typical entrypoint flow:

- Declare ``lifespan(scraper: AIOScraper)`` as an async context manager.
- Register scrapers inside the context manager.
- Optionally add pipelines and middlewares before yielding control.

Launch the CLI with either a file path (``aioscraper scraper.py`` looks for ``lifespan``) or an explicit module and callable (``aioscraper mypkg.scraper:custom_lifespan``).

Configuration
-------------

Configuration precedence: CLI flags -> environment variables -> :class:`aioscraper.config.Config` defaults.

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
