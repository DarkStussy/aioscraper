Callbacks and Error Handling
============================

Callbacks drive the happy path, while error handlers keep failures contained. `aioscraper` routes both through the request lifecycle so you can react at the right moment.

.. rubric:: Key points

- ``Request.callback`` runs only on successful responses.
- ``Request.errback`` handles HTTP statuses ``>=400`` and unexpected exceptions from callbacks or middlewares.
- ``Request.cb_kwargs`` are merged into callback/errback arguments alongside framework dependencies (``send_request``, ``pipeline``, etc.).
- Use ``@compiled`` decorator on callbacks for optimized dependency injection.


.. code-block:: python

    import logging

    from aioscraper import AIOScraper, Request, Response, SendRequest, Pipeline
    from aioscraper.exceptions import HTTPException

    scraper = AIOScraper()


    @scraper
    async def scrape(send_request: SendRequest):
        await send_request(
            Request(
                url="https://example.com/api/article",
                callback=handle_response,
                errback=handle_error,
            )
        )


    async def handle_response(response: Response, pipeline: Pipeline):
        # process data
        ...


    async def handle_error(exc: Exception, request: Request):
        if isinstance(exc, HTTPException):
            logging.warning("HTTP %s for %s", exc.status_code, request.url)
        else:
            logging.exception("Unhandled error for %s", request.url)


Optimizing callbacks
---------------------------------------

By default, `aioscraper` uses runtime inspection to inject dependencies into callbacks. For performance-critical scrapers, use the ``@compiled`` decorator to pre-compute parameter filtering at import time.

.. code-block:: python

    from aioscraper import AIOScraper, Request, Response, SendRequest, compiled

    scraper = AIOScraper()


    @scraper
    async def scrape(send_request: SendRequest):
        await send_request(Request(url="https://api.example.com/data", callback=parse))


    @compiled
    async def parse(response: Response, send_request: SendRequest):
        # Dependencies injected with zero runtime overhead
        data = await response.json()
        # process data...


The ``@compiled`` decorator:

- Caches function parameters at import time instead of inspecting on every call
- Eliminates repeated ``inspect.signature()`` calls from the hot path
- Provides ~10-30% performance improvement for callback execution
- Works with both callbacks and errbacks
- Maintains full compatibility with dependency injection


.. autoclass:: aioscraper.types.session.Request
   :members:
   :no-index:

.. autofunction:: aioscraper.compiled
   :no-index: