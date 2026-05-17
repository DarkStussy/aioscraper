Middlewares
===========

Middlewares wrap the entire request lifecycle with a flexible ``call_next`` chain. Each middleware is a factory that receives any dependencies registered on the scraper (e.g. ``send_request``) and returns the actual middleware callable.

The middleware signature is ``async def middleware(call_next, request) -> Response | None``:

- Modify ``request`` before invoking ``call_next`` to influence dispatch (headers, auth, tracing).
- Inspect or transform the ``Response`` returned by ``call_next`` before the callback runs.
- Wrap ``call_next`` in ``try/except`` to handle exceptions; re-raise to route them to the request's errback.
- Return ``None`` (with or without calling ``call_next``) to signal that the middleware handled the request itself - the orchestrator will skip both the callback and the errback for this attempt.

.. code-block:: python

    from aioscraper import AIOScraper, Request, Response
    from aioscraper.exceptions import HTTPException
    from aioscraper.types import RequestHandler, RequestMiddleware, SendRequest

    scraper = AIOScraper()


    @scraper.middleware
    def logging_middleware() -> RequestMiddleware:
        async def middleware(call_next: RequestHandler, request: Request) -> Response | None:
            print("dispatching", request.url)
            try:
                response = await call_next(request)
            except HTTPException as exc:
                print("error", exc.status_code, request.url)
                raise
            if response is not None:
                print("response", response.status, "for", request.url)
            return response

        return middleware


    @scraper.middleware
    def auth_middleware(api_token: str) -> RequestMiddleware:
        async def middleware(call_next: RequestHandler, request: Request) -> Response | None:
            request.headers = {**(request.headers or {}), "Authorization": f"Bearer {api_token}"}
            return await call_next(request)

        return middleware

Factories receive injected dependencies via parameter names (same convention as callbacks and pipeline global middlewares). ``send_request`` is always available; user-registered ``scraper.add_dependencies(...)`` values are matched by parameter name.

Order
-----

Middlewares are composed in *registration order*: the first registered factory becomes the outermost wrapper (runs first when entering, last when unwinding); the last registered becomes the innermost (closest to dispatch). If you need a middleware to wrap another, register it first.

.. code-block:: python

    @scraper.middleware
    def trace_middleware() -> RequestMiddleware: ...

    scraper.middleware.add(other_factory)


Built-in middlewares
--------------------

The framework provides built-in middlewares that integrate into the same chain and can be enabled through configuration.

Retry Middleware
~~~~~~~~~~~~~~~~

The :class:`RetryMiddleware <aioscraper.middlewares.retry.RetryMiddleware>` is enabled through :ref:`retry config <retry-config>`.

When active, it wraps ``call_next`` and, on a matching status code or exception, re-enqueues the request with the configured backoff. The current attempt is short-circuited (no errback is fired) until the maximum number of attempts is exhausted, at which point the exception is propagated to the errback.
