Middlewares
===========

Middlewares let you intercept requests, responses and exceptions. Each hook runs at a specific phase and can be registered with decorators.

- ``@scraper.middleware("outer")`` — before a request enters the queue (normalize/annotate requests).
- ``@scraper.middleware("inner")`` — right before HTTP dispatch (headers, auth, tracing); :class:`StopMiddlewareProcessing <aioscraper.exceptions.StopMiddlewareProcessing>` stops remaining inner middlewares, :class:`StopRequestProcessing <aioscraper.exceptions.StopRequestProcessing>` stops the request entirely.
- ``@scraper.middleware("exception")`` — whenever sending/handling fails; :class:`StopMiddlewareProcessing <aioscraper.exceptions.StopMiddlewareProcessing>` stops further exception handling/errback, :class:`StopRequestProcessing <aioscraper.exceptions.StopRequestProcessing>` stops request processing.
- ``@scraper.middleware("response")`` — after HTTP completes, before ``callback``; :class:`StopMiddlewareProcessing <aioscraper.exceptions.StopMiddlewareProcessing>` stops remaining response middlewares, :class:`StopRequestProcessing <aioscraper.exceptions.StopRequestProcessing>` stops further handling of the response.


.. code-block:: python

    from aioscraper import AIOScraper
    from aioscraper.types import Request, Response

    scraper = AIOScraper()


    @scraper.middleware("outer")
    async def log_queue(request: Request):
        print("queued", request.url)


    @scraper.middleware("inner")
    async def add_headers(request: Request):
        request.headers = {**(request.headers or {}), "User-Agent": "aioscraper"}


    @scraper.middleware("exception")
    async def handle_exception(exc: Exception):
        print("exception", exc)


    @scraper.middleware("response")
    async def log_response(response: Response, request: Request):
        print("response", response.status, "for", request.url)
