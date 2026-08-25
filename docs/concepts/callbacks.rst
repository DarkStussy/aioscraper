Callbacks and Error Handling
============================

A callback handles a successful response; an errback handles a terminal failure, including one raised by the callback. Depending on the outcome, either, both, or neither may run.

.. rubric:: Key points

- ``callback`` runs on a response with a status below ``400``.
- ``errback`` handles statuses ``>=400``, transport failures, and anything a callback or middleware raised.
- Neither runs when the attempt was retried, when a middleware returned ``None``, or when the request set no handler for what happened.
- A failure with no ``errback`` is logged and recorded in :ref:`RunResult <unhandled-errors>` instead.
- Both receive ``Request.cb_kwargs`` and the run's dependencies (``send_request``, ``pipeline``, ...), matched by parameter name.
- An ``errback`` that raises turns both exceptions into an ``ExceptionGroup``, which is then recorded.


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


.. _response-body:

Reading the response body
-------------------------

The body is streamed from the open connection, which the backend closes once the middleware chain and
the callback return. **The body must be consumed inside the callback**: a :class:`Response
<aioscraper.types.session.Response>` read after that has no connection left to read from.

- :meth:`read() <aioscraper.types.session.Response.read>` buffers the whole body, so ``read()``,
  :meth:`text() <aioscraper.types.session.Response.text>` and
  :meth:`json() <aioscraper.types.session.Response.json>` can be called repeatedly.
- :meth:`iter_bytes() <aioscraper.types.session.Response.iter_bytes>` streams it chunk by chunk and
  buffers nothing. Breaking out of the loop early is allowed; the rest of the body is discarded when
  the request context closes. Iterating a body that :meth:`read` already buffered replays it from
  memory.
- Mixing the two on an unbuffered body raises :class:`StreamConsumed
  <aioscraper.exceptions.StreamConsumed>`: after streaming, ``read()`` has nothing left to return.

.. code-block:: python

    import hashlib

    from aioscraper.types import Response


    async def checksum(response: Response) -> str:
        digest = hashlib.sha256()
        async for chunk in response.iter_bytes():
            digest.update(chunk)

        return digest.hexdigest()

The callback runs on the event loop, so a sink that blocks - a file, a socket, a database driver
without async support - has to be pushed off it, for example with ``asyncio.to_thread``.

:ref:`max_response_body_size <body-limits>` applies to both reads, so an oversized body raises
:class:`ResponseTooLarge <aioscraper.exceptions.ResponseTooLarge>` inside the callback, which routes it
to ``errback``.

Optimizing callbacks
--------------------

Deciding what to pass a callback means inspecting its signature, which by default happens on every call. ``@compiled`` does it once, at import time, and keeps the parameter names on the wrapper.

.. code-block:: python

    from aioscraper import AIOScraper, Request, Response, SendRequest, compiled

    scraper = AIOScraper()


    @scraper
    async def scrape(send_request: SendRequest):
        await send_request(Request(url="https://api.example.com/data", callback=parse))


    @compiled
    async def parse(response: Response, send_request: SendRequest):
        data = await response.json()
        # process data...


It works on callbacks and errbacks alike, and changes nothing about which arguments they receive. Worth it where a callback runs thousands of times; not worth the import elsewhere.


.. autoclass:: aioscraper.types.session.Request
   :members:
   :no-index:

.. autofunction:: aioscraper.compiled
   :no-index: