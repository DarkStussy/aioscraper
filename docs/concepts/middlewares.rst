Middlewares
===========

Middlewares let you intercept requests, responses and exceptions. Each hook runs at a specific phase and can be registered with decorators.

- ``@scraper.middleware("outer")`` — before a request enters the queue (normalize/annotate requests).
- ``@scraper.middleware("inner")`` — right before HTTP dispatch (headers, auth, tracing).
- ``@scraper.middleware("exception")`` — whenever sending/handling fails.
- ``@scraper.middleware("response")`` — after HTTP completes, before ``callback``.

:class:`StopMiddlewareProcessing <aioscraper.exceptions.StopMiddlewareProcessing>` stops remaining middlewares in the current phase (inner/response/exception); :class:`StopRequestProcessing <aioscraper.exceptions.StopRequestProcessing>` stops the current request entirely.


.. code-block:: python

    from aioscraper import AIOScraper, Request, Response

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

Built-in retry middleware
-------------------------

`aioscraper` ships with :class:`RetryMiddleware <aioscraper.middlewares.retry.RetryMiddleware>`. Enable it by configuring ``SessionConfig.retry`` (see :ref:`retry-config`).
Once enabled, it is registered automatically in the exception phase and re-queues requests when the configured status codes or exceptions occur.

Priority
--------

Middlewares run in ascending ``priority`` order (default ``100``). When registering via ``scraper.middleware.add`` or the decorator helper, pass ``priority=10`` (or any integer) to control execution ordering:

.. code-block:: python

    @scraper.middleware("inner", priority=5)
    async def set_headers(request: Request):
        ...

    scraper.middleware.add("inner", other_inner_middleware, priority=20)
