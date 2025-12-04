Overview
========

`aioscraper` orchestrates asynchronous scrapers, middleware, and pipelines to handle high-volume web requests with low latency.

Installation
------------

.. code-block:: bash

   pip install aioscraper


Example
-----------


Create ``scraper.py``:

.. code-block:: python

    from contextlib import asynccontextmanager

    from aioscraper import AIOScraper
    from aioscraper.types import Request, Response, SendRequest


    async def scrape(send_request: SendRequest):
        await send_request(Request(url="https://example.com", callback=handle_response))


    async def handle_response(response: Response):
        print(f"Fetched {response.url} with status {response.status}")


    @asynccontextmanager
    async def lifespan(scraper: AIOScraper):
        scraper.register(scrape)
        yield
        # cleanup some resources...

Run:

.. code-block:: bash

   aioscraper scraper

See :doc:`cli` for entrypoint patterns and configuration options.

Execution flow
--------------
1. You register scrapers; each uses `send_request` to enqueue work.
2. The scheduler dispatches requests respecting priorities and configured concurrency.
3. Session adapters (e.g., aiohttp) perform HTTP calls and return `Response` objects.
4. Callbacks handle responses and can push items into pipelines.
5. Pipelines run their stages and middlewares, then gracefully shut down with the executor.
