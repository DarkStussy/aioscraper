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

- Without ``:attr``: the CLI looks for a ``scraper`` attribute that is either an :class:`AIOScraper <aioscraper.scraper.core.AIOScraper>` instance or a callable returning one.
- With ``:attr`` pointing to an :class:`AIOScraper <aioscraper.scraper.core.AIOScraper>`: the CLI uses that instance.
- With ``:attr`` pointing to a callable (sync **or async**): the CLI executes/awaits it and expects an :class:`AIOScraper <aioscraper.scraper.core.AIOScraper>` instance in return.

Examples:

.. code-block:: bash

   aioscraper scraper                   # uses scraper variable from scraper.py
   aioscraper mypkg.scraper:custom_app  # uses custom_app AIOScraper instance
   aioscraper mypkg.factory:make        # calls make() (sync factory)
   aioscraper mypkg.factory:make_async  # awaits make_async() (async factory)

For resource setup/teardown around the same scraper instance, attach a ``lifespan(scraper)`` when constructing the scraper in code (see :doc:`/concepts/lifespan`).

Running without the CLI
-----------------------

You can run the same scraper programmatically using :func:`run_scraper <aioscraper.scraper.runner.run_scraper>`:

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

Configuration
-------------

Configuration precedence (when the CLI needs to load a config): CLI flags -> environment variables -> :class:`Config <aioscraper.config.Config>` defaults. If the resolved :class:`AIOScraper <aioscraper.scraper.core.AIOScraper>` already has ``config`` set, the CLI leaves it untouched and CLI flags/env vars are ignored.

- ``--concurrent-requests``: Max concurrent requests (overrides ``SCHEDULER_CONCURRENT_REQUESTS``).
- ``--pending-requests``: Pending requests to keep queued (overrides ``SCHEDULER_PENDING_REQUESTS``).

Supported environment variables:

- ``SESSION_REQUEST_TIMEOUT``: Request timeout (seconds).
- ``SESSION_REQUEST_DELAY``: Delay between requests (seconds).
- ``SESSION_SSL``: ``true``/``false`` to toggle verification, or a path to a CA bundle for custom certificates.
- ``SESSION_PROXY``: Default proxy for the HTTP client (string ``http://user:pass@host:port`` or JSON ``{"http": "...", "https": "..."}``).
- ``SESSION_HTTP_BACKEND``: Force ``aiohttp`` or ``httpx`` regardless of what is installed (falls back automatically otherwise).
- ``SCHEDULER_CONCURRENT_REQUESTS``: Max concurrent requests.
- ``SCHEDULER_PENDING_REQUESTS``: Pending requests to maintain.
- ``SCHEDULER_CLOSE_TIMEOUT``: Scheduler shutdown timeout (seconds).
- ``EXECUTION_TIMEOUT``: Global execution timeout (seconds).
- ``EXECUTION_SHUTDOWN_TIMEOUT``: Graceful shutdown timeout (seconds).
- ``EXECUTION_SHUTDOWN_CHECK_INTERVAL``: Interval between shutdown checks (seconds).
- ``EXECUTION_LOG_LEVEL``: Log level name used when timeouts occur (e.g., ``WARNING``, ``ERROR``).
- ``PIPELINE_STRICT``: Whether to raise when an item references a missing pipeline.
