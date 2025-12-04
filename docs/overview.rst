Overview
========

`aioscraper` orchestrates asynchronous scrapers, middleware, and pipelines to handle high-volume web requests with low latency.

Installation
------------

.. code-block:: bash

   pip install aioscraper


Example
-----------

.. code-block:: python

   import asyncio

   from aioscraper import AIOScraper
   from aioscraper.types import Request, SendRequest, Response


   async def scraper(send_request: SendRequest) -> None:
       await send_request(Request(url="https://example.com", callback=handle_response))


   async def handle_response(response: Response) -> None:
       print(f"Fetched {response.url} with status {response.status}")


   async def main():
       async with AIOScraper(scraper) as s:
           await s.start()


   if __name__ == "__main__":
       asyncio.run(main())

Execution flow
--------------
1. You register scrapers; each uses `send_request` to enqueue work.
2. The scheduler dispatches requests respecting priorities and configured concurrency.
3. Session adapters (e.g., aiohttp) perform HTTP calls and return `Response` objects.
4. Callbacks handle responses and can push items into pipelines.
5. Pipelines run their stages and middlewares, then gracefully shut down with the executor.
