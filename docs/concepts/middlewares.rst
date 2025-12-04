Middlewares
===========

Middlewares let you intercept requests, responses, exceptions, and pipeline items. Each hook runs at a specific phase.

Hooks
-----
- ``add_outer_request_middlewares`` — before a request enters the queue (normalize/annotate requests).
- ``add_inner_request_middlewares`` — right before HTTP dispatch (headers, auth, tracing).
- ``add_request_exception_middlewares`` — whenever sending/handling fails; can stop further handling with :class:`aioscraper.exceptions.StopMiddlewareProcessing`.
- ``add_response_middlewares`` — after HTTP completes, before `callback`.
- ``add_pipeline_pre_processing_middlewares`` / ``add_pipeline_post_processing_middlewares`` — around pipeline processing.

Example
-------

.. code-block:: python

   from aioscraper import AIOScraper
   from aioscraper.types import Request, Response

   scraper = AIOScraper()

   async def log_queue(request: Request):
       print("queued", request.url)

   async def add_headers(request: Request):
       request.headers = {**(request.headers or {}), "User-Agent": "aioscraper"}

   async def log_response(response: Response, request: Request):
       print("response", response.status, "for", request.url)

   async def audit_item(item):
       print("item processed:", item)

   scraper.add_outer_request_middlewares(log_queue)
   scraper.add_inner_request_middlewares(add_headers)
   scraper.add_response_middlewares(log_response)
   scraper.add_pipeline_post_processing_middlewares(audit_item)
