# Changelog

## Unreleased

### Added
- `AIOScraper(http_client=...)`, taking an existing `aiohttp.ClientSession` or `httpx.AsyncClient`. It selects the backend, is used as configured, and is left open when the run ends. `get_sessionmaker()` takes the same `client` argument. Mutually exclusive with `sessionmaker_factory`.
- `BaseSession.owns_client` and the `client`/`owns_client` arguments of `AiohttpSession` and `HttpxSession`, which say who closes the underlying client. `owns_client=False` without a `client` raises `ValueError`.
- `RequestRetryConfig.methods` (`SESSION_RETRY_METHODS`), the HTTP methods a retry may replay. Defaults to `GET`, `HEAD`, `OPTIONS`, `TRACE`; matching is case-insensitive.
- `Request.retryable`, a per-request override of that method check: `True` retries, `False` never does, `None` defers to `methods`.
- `Response.iter_bytes()`, a backend-neutral body stream. Breaking out early is supported; the connection is released when the request context closes.
- `Response.read(limit=...)` for a bounded read, itself capped by `max_response_body_size`, and `StreamConsumed`, raised when a body is read after its stream was consumed.
- `SessionConfig.max_response_body_size` (`SESSION_MAX_RESPONSE_BODY_SIZE`), enforced by `read()` and `iter_bytes()` at the chunk that crosses it. Defaults to `None` (unlimited); crossing it raises `ResponseTooLarge`.
- `SessionConfig.max_error_body_size` (`SESSION_MAX_ERROR_BODY_SIZE`), default 64 KiB. A failed response is read only up to that many bytes for the `HTTPException` message, which ends with `[truncated]` when the body was longer.
- `RunResult`, returned by `run_scraper()`, `AIOScraper.wait()` and `AIOScraper.shutdown()`: `errors`, `error_counts`, `total_errors`, `interrupted`, `timed_out` and `ok`.
- `RunResult.requests_started`, `requests_succeeded`, `requests_failed` and `items_processed`, counted per attempt. `requests_failed` covers failures an `errback` handled, unlike `error_counts`.
- `AIOScraper.result`, the `RunResult` as it stands.
- `--allow-partial-success`, which makes the CLI exit `0` despite recorded errors, overriding `EXECUTION_ON_ERROR`.
- `RequestRetryConfig.should_retry(request, exc, retries)`, deciding failures the `statuses`/`exceptions` match cannot express. `None` falls back to that match; the method check still applies first.

### Changed
- **BREAKING:** a request is retried only when its method is listed in `methods`. A `POST`/`PATCH` that reached the server before the connection dropped was replayed, duplicating the effect. Opt back in via `methods` or `Request.retryable=True`; sending an idempotency key stays the application's job.
- **BREAKING:** `BaseSession.close()` is no longer abstract: it closes the client only when the session owns it, and backends implement `_close_client()` instead. Custom backends must rename their `close()`. The session constructors are keyword-only.
- **BREAKING:** `Response` takes `aiter_bytes` (a chunk iterator factory) and `max_body_size` instead of `read`. Custom `BaseSession` backends must be updated.
- **BREAKING:** `execution.on_error` defaults to `ErrorPolicy.FAIL`. A CLI run that lost data used to exit `0`. Partial success is now opt-in through `EXECUTION_ON_ERROR=log` or `--allow-partial-success`.
- **BREAKING:** `run_scraper()` returns a `RunResult` instead of the `interrupted` flag; the flag is `result.interrupted`. `AIOScraper.wait()` and `shutdown()` return one too, where they returned `None`.
- **BREAKING:** the CLI exits `124` when `execution.timeout` expires; it exited `0` unless errors were recorded. Neither `ErrorPolicy.LOG` nor `--allow-partial-success` waives it: they cover recorded errors, not work the run never attempted.
- **BREAKING:** retries are applied by the dispatcher around the whole middleware chain instead of by a middleware inside it. `RetryMiddleware` and the `aioscraper.middlewares` package are removed; use `SessionConfig.retry` and `should_retry`. A failure now reaches the middlewares above it on every attempt instead of being swallowed below them, and one raised by a middleware — including on a `200` — goes through the retry policy too. Callback failures are still never retried.
- **BREAKING:** `PRequest` is now `Attempt` and carries the retry count; the framework no longer writes to `Request`. A request sent twice used to share one retry counter through `Request.state`, so concurrent sends split a single retry budget and a reused object inherited the previous run's count.
- **BREAKING:** an `AIOScraper` instance is single-use. `start()` and `async with` raise `RuntimeError` on a second run instead of silently doing nothing, and `wait()`/`shutdown()` raise it when the scraper was never started instead of reporting a clean result. A closed scraper returns its recorded `RunResult` from both, `timed_out` included.
- Concurrent lifecycle calls no longer step on each other: concurrent entries no longer set the lifespan up twice, a failed start leaves the instance startable, concurrent `close()` calls wait for the first teardown, a `close()` during startup waits for it to settle, and a `wait()` in flight when `close()` cancels the run reports that run instead of raising `CancelledError`.
- `Request.delay` applies to every send. The delayed heap used to clear it on the request object, so sending the same object again after its first delay skipped the delay entirely.
- The httpx backend sends with `stream=True` and closes the response through the request context; httpx buffered the whole body inside `send()` before any limit could apply.

### Fixed
- An error response is no longer buffered whole to build the `HTTPException` message.

## 0.12.0 (2026-08-15)

### Added
- `SECURITY.md`.
- `py.typed` marker.
- `UnsupportedRequestOption`, raised by the httpx backend for `Request.proxy`, `proxy_auth`, `proxy_headers` and a non-default `max_redirects`. They were silently dropped before, sending traffic past the configured proxy.
- `AIOScraper.errors` and `AIOScraper.error_counts`: unhandled request failures, failing errbacks and resource-close failures are recorded, not only logged.
- `execution.on_error` (`EXECUTION_ON_ERROR`). `ErrorPolicy.FAIL` makes the CLI exit `1` when a run recorded errors; the default `LOG` exits `0`.

### Changed
- **BREAKING:** the httpx backend rejects the options above instead of ignoring them. Use the aiohttp backend, or `SessionConfig.proxy`.
- The httpx client is pinned to the `Request.max_redirects` default; it used its own default of 20.
- `run_scraper()` returns `True` when a signal stopped the run, and the CLI exits `130` instead of `0`.
- Lowered the `aiohttp` and `aiohttp-speedups` extras floor to `>=3.12.0` (was `>=3.13.2`).
- Locked `aiohttp` bumped to 3.14.3, clearing 14 advisories against 3.13.5.
- `docs/changelog.rst` includes `CHANGELOG.md` via `myst-parser` instead of duplicating it.
- Tests run with `filterwarnings = ["error"]` and a 60s per-test timeout; docs build with `fail_on_warning`.
- CI also runs the docs build, a coverage gate, `pip-audit`, a wheel install smoke test, and the suite against the lowest supported dependencies.
- Publishing to PyPI requires the tag to match `project.version`, a matching `CHANGELOG.md` section, and green test and docs workflows.

### Fixed
- On SIGINT/SIGTERM in-flight work gets `execution.shutdown_timeout` to finish instead of being cancelled immediately.
- `execution.shutdown_check_interval` is applied as the queue poll timeout instead of a hard-coded `0.05s`, and now caps it: a retry parked for 60s used to delay shutdown by 60s.
- Request outcomes are recorded at the transport level: a `429`/`503` re-queued by `RetryMiddleware` reaches the adaptive rate limiter as a failure instead of a success.
- Callback errors no longer count as transport failures for the adaptive rate limiter.
- `SCHEDULER_READY_QUEUE_MAX_SIZE` is read by `load_config()`; it was documented but ignored.
- `scheduler.ready_queue_max_size` also counts delayed retries and requests parked in a rate limiter group, which bypassed it before. It throttles the scraper entrypoint; sends from inside a job are counted but never blocked.
- httpx backend uses `build_request()` + `send()`; per-request `cookies=` on `request()` is deprecated in httpx.
- Quick Start snippets in `README.md` and `docs/quickstart.rst` are valid Python.
- Quick Start env var names: `SESSION_RETRY_ENABLED`, `SESSION_RETRY_ATTEMPTS`, `SESSION_RATE_LIMIT_ENABLED`, `SESSION_RATE_LIMIT_INTERVAL`.
- Read the Docs installs the `aiohttp`/`httpx` extras, so autodoc can import the session backends.

## 0.11.0 (2026-05-18)

### Added
- Lazy response body reads inside request middlewares — the response connection is kept open by a per-request `AsyncExitStack` until the whole chain and the callback finish.

### Changed
- **BREAKING:** Reworked request middlewares to a `call_next`-style chain. The `outer`/`inner`/`response`/`exception` stages are gone; each middleware is now a factory returning `async def mw(call_next, request) -> Response | None`. Registration order is the wrapping order (first registered = outermost).
- **BREAKING:** `RetryMiddleware` rewritten to the new contract. Receives `send_request` via DI.
- **BREAKING:** `get_sessionmaker` now accepts a `SessionConfig` instead of the full `Config`.

### Removed
- **BREAKING:** `StopRequestProcessing` exception — return `None` from a middleware to short-circuit without calling the errback.
- **BREAKING:** `MiddlewareConfig`, `RequestRetryConfig.middleware`, middleware priority, and the `SESSION_RETRY_MIDDLEWARE_PRIORITY` env var. Ordering is now controlled solely by registration order.

## 0.10.4 (2025-12-13)

### Changed
- Split aiohttp dependency into `aiohttp` and `aiohttp-speedups` extras for optional speedups installation

## 0.10.3 (2025-12-12)

### Added
- `@compiled` decorator for optimized dependency injection in callbacks

## 0.10.2 (2025-12-10)

### Changed
- Renamed `RateLimiterManager` to `RateLimitManager` for consistency
- Replaced Pyright with BasedPyright for type checking
- Replaced Flake8 and Black with Ruff for linting and formatting

### Fixed
- Graceful shutdown in rate limit manager

## 0.10.1 (2025-12-09)

### Added
- Queue consumer example
- Lifespan tests

### Changed
- Improved configuration validation
- Improved logging

### Fixed
- Lifespan startup order (ensure lifespan starts before main start)

## 0.10.0 (2025-12-09)

### Added
- Rate limiting with configurable RPS and burst limits
- Adaptive rate limiter that adjusts based on server responses (429, 503)
- Retry backoff configuration (constant, linear, exponential)
- Retry-After header support

### Changed
- Simplified AIOScraper API for easier integration with web frameworks
- Improved request manager shutdown handling

## 0.9.0 (2025-12-07)

### Added
- httpx client support (alternative to aiohttp)
- Retry middleware with configurable attempts and status codes
- Global pipeline middleware
- SessionConfig.proxy for per-session proxy configuration
- Async response read for better streaming support

### Changed
- Refactored core module structure
- Improved middleware flow and pipeline registration

## 0.8.0 (2025-12-04)

### Added
- CLI interface with environment-based configuration
- CLI uvloop support for better performance
- Graceful shutdown handling
- Python 3.14 support

### Changed
- Improved error handling in request manager

### Removed
- Python 3.10 support
