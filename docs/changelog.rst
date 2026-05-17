Changelog
=========

.. _changelog-0-11-0:

0.11.0 (2026-05-18)
-------------------

Added
~~~~~
- Lazy response body reads inside request middlewares — the response connection is kept open by a per-request ``AsyncExitStack`` until the whole chain and the callback finish.

Changed
~~~~~~~
- **BREAKING:** Reworked request middlewares to a ``call_next``-style chain. The ``outer``/``inner``/``response``/``exception`` stages are gone; each middleware is now a factory returning ``async def mw(call_next, request) -> Response | None``. Registration order is the wrapping order (first registered = outermost).
- **BREAKING:** ``RetryMiddleware`` rewritten to the new contract. Receives ``send_request`` via DI.
- **BREAKING:** ``get_sessionmaker`` now accepts a ``SessionConfig`` instead of the full ``Config``.

Removed
~~~~~~~
- **BREAKING:** ``StopRequestProcessing`` exception — return ``None`` from a middleware to short-circuit without calling the errback.
- **BREAKING:** ``MiddlewareConfig``, ``RequestRetryConfig.middleware``, middleware priority, and the ``SESSION_RETRY_MIDDLEWARE_PRIORITY`` env var. Ordering is now controlled solely by registration order.

.. _changelog-0-10-3:

0.10.3 (2025-12-12)
-------------------

Added
~~~~~
- ``@compiled`` decorator for optimized dependency injection in callbacks

.. _changelog-0-10-2:

0.10.2 (2025-12-10)
-------------------

Changed
~~~~~~~
- Renamed ``RateLimiterManager`` to ``RateLimitManager`` for consistency
- Replaced Pyright with BasedPyright for type checking
- Replaced Flake8 and Black with Ruff for linting and formatting

Fixed
~~~~~
- Graceful shutdown in rate limit manager

.. _changelog-0-10-1:

0.10.1 (2025-12-09)
-------------------

Added
~~~~~
- Queue consumer example
- Lifespan tests

Changed
~~~~~~~
- Improved configuration validation
- Improved logging

Fixed
~~~~~
- Lifespan startup order (ensure lifespan starts before main start)

.. _changelog-0-10-0:

0.10.0 (2025-12-09)
-------------------

Added
~~~~~
- Rate limiting with configurable RPS and burst limits
- Adaptive rate limiter that adjusts based on server responses (429, 503)
- Retry backoff configuration (constant, linear, exponential)
- Retry-After header support

Changed
~~~~~~~
- Simplified AIOScraper API for easier integration with web frameworks
- Improved request manager shutdown handling

.. _changelog-0-9-0:

0.9.0 (2025-12-07)
------------------

Added
~~~~~
- httpx client support (alternative to aiohttp)
- Retry middleware with configurable attempts and status codes
- Global pipeline middleware
- SessionConfig.proxy for per-session proxy configuration
- Async response read for better streaming support

Changed
~~~~~~~
- Refactored core module structure
- Improved middleware flow and pipeline registration

.. _changelog-0-8-0:

0.8.0 (2025-12-04)
------------------

Added
~~~~~
- CLI interface with environment-based configuration
- CLI uvloop support for better performance
- Graceful shutdown handling
- Python 3.14 support

Changed
~~~~~~~
- Improved error handling in request manager

Removed
~~~~~~~
- Python 3.10 support
