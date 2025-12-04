Callbacks and Error Handling
============================

Callbacks drive the happy path, while error handlers keep failures contained. `aioscraper` routes both through the request lifecycle so you can react at the right moment.

Key points
----------
- `Request.callback` runs only on successful responses.
- `Request.errback` handles HTTP statuses ``>=400`` and unexpected exceptions from callbacks or middlewares.
- `request_exception_middlewares` see exceptions before `errback`; raise :class:`aioscraper.exceptions.StopMiddlewareProcessing` to suppress further handling.
- `cb_kwargs` are merged into callback/errback arguments alongside framework dependencies (``send_request``, ``pipeline``, etc.).

Example
-------

.. code-block:: python

   import logging
   from dataclasses import dataclass

   from aioscraper import AIOScraper
   from aioscraper.exceptions import HTTPException, StopMiddlewareProcessing
   from aioscraper.types import Request, Response, SendRequest, Pipeline

   scraper = AIOScraper()

   @dataclass(slots=True)
   class Article:
       title: str
       pipeline_name: str = "articles"

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
       data = response.json()
       await pipeline(Article(title=data["title"]))

   async def handle_error(exc: Exception, request: Request):
       if isinstance(exc, HTTPException):
           logging.warning("HTTP %s for %s", exc.status_code, request.url)
       else:
           logging.exception("Unhandled error for %s", request.url)

   async def swallow_404(exc: Exception, request: Request):
       if isinstance(exc, HTTPException) and exc.status_code == 404:
           raise StopMiddlewareProcessing()

   scraper.add_request_exception_middlewares(swallow_404)
