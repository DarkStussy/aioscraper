Middlewares
===========

Middlewares let you intercept requests, responses and exceptions. Each hook runs at a specific phase.

- :meth:`add_outer_request_middlewares <aioscraper.scraper.core.AIOScraper.add_outer_request_middlewares>` — before a request enters the queue (normalize/annotate requests).
- :meth:`add_inner_request_middlewares <aioscraper.scraper.core.AIOScraper.add_inner_request_middlewares>` — right before HTTP dispatch (headers, auth, tracing).
- :meth:`add_request_exception_middlewares <aioscraper.scraper.core.AIOScraper.add_request_exception_middlewares>` — whenever sending/handling fails; can stop further handling with :class:`StopMiddlewareProcessing <aioscraper.exceptions.StopMiddlewareProcessing>`.
- :meth:`add_response_middlewares <aioscraper.scraper.core.AIOScraper.add_response_middlewares>` — after HTTP completes, before ``callback``.


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


    async def handle_exception(exc: Exception):
        print("exception", exc)


    scraper.add_outer_request_middlewares(log_queue)
    scraper.add_inner_request_middlewares(add_headers)
    scraper.add_response_middlewares(log_response)
    scraper.add_request_exception_middlewares(handle_exception)
