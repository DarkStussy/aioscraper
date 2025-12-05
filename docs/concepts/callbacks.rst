Callbacks and Error Handling
============================

Callbacks drive the happy path, while error handlers keep failures contained. `aioscraper` routes both through the request lifecycle so you can react at the right moment.

.. rubric:: Key points

- ``Request.callback`` runs only on successful responses.
- ``Request.errback`` handles HTTP statuses ``>=400`` and unexpected exceptions from callbacks or middlewares.
- ``Request.cb_kwargs`` are merged into callback/errback arguments alongside framework dependencies (``send_request``, ``pipeline``, etc.).


.. code-block:: python

    import logging

    from aioscraper import AIOScraper
    from aioscraper.exceptions import HTTPException
    from aioscraper.types import Request, Response, SendRequest, Pipeline

    scraper = AIOScraper()


    @scraper.register
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


.. autoclass:: aioscraper.types.session.Request
   :members:
   :no-index:
