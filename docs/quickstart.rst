Quickstart
==========

Get running in minutes. You'll build a tiny scraper, see the full request/response flow, and run it from the CLI.

Before you start, install ``aioscraper`` - see :doc:`installation` for requirements and options.

Create your first scraper
-------------------------

Save as ``scraper.py``:

.. code-block:: python

   from aioscraper import AIOScraper, Request, Response, SendRequest


   scraper = AIOScraper()


   @scraper
   async def scrape(send_request: SendRequest):
       for i in range(1, 4):
           await send_request(
               Request(
                   url=f"https://example.com/?i={i}",
                   callback=handle_response,
                   cb_kwargs={"i": i},
               )
           )


   async def handle_response(response: Response, i: int):
       print(f"[{response.status}] {i}: {response.url}")

What this code does
-------------------
- Creates one ``AIOScraper`` instance.
- Adds a scraper that queues three GET requests (each tagged with its index).
- Prints status and URL for each response as it arrives.


Run it

.. code-block:: bash

   aioscraper scraper

What happens when it runs
-------------------------
- The CLI loads your module and finds the ``scraper`` instance.
- The ``scrape`` function enqueues several requests (each with its own callback arguments).
- The scheduler dispatches them using your concurrency settings; HTTP clients execute without blocking each other, so responses can arrive out of order.
- As responses arrive, ``handle_response`` runs for each one and prints status/URL.

Add your own requests and logic
-------------------------------
- Change the URLs to target your APIs or pages.
- Add query params/headers by passing them to :class:`Request <aioscraper.types.session.Request>`.
- Parse response data inside ``handle_response`` and push items into pipelines (see :doc:`concepts/pipelines`).

Next steps
----------
- Configure via env/CLI flags (see :doc:`cli`).
- Add middlewares (see :doc:`concepts/middlewares`).
- Wrap setup/teardown in a lifespan context manager (see :doc:`concepts/lifespan`).
