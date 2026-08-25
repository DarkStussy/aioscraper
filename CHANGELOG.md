# Changelog

## Unreleased

### Added
- `RateLimitConfig.group_concurrency` (`SESSION_RATE_LIMIT_GROUP_CONCURRENCY`), a cap on one rate limit group's requests in flight. `scheduler.concurrent_requests` is a single global limit, so requests waiting on a slow host held slots every other group would otherwise use, and the limit had to be sized for the slowest target. The cap is applied at admission: a group hands the scheduler at most that many attempts and releases the next when a request finishes, so an attempt waiting on its group holds no scheduler slot. Not a reservation — groups still draw from the same `concurrent_requests`. Requires `per_group`, `0` for no ceiling.
- `GroupPolicy`, the named return type of a `group_by`, which can give a group its own ceiling instead of the configured one.

### Fixed
- A rate limit group is no longer reported idle while an attempt it has taken off its queue is still on its way to the scheduler or in flight. The run's completion check reads those queues, so it could find them all empty and finish while an attempt was still to send; the idle timeout could also retire a group whose requests were still running, and the next group under that key started with a full ceiling beside them.
- A rate limit group retiring on its idle timeout reports it once rather than twice, from the worker's done callback alone. The manager dropped the second report because the group was already gone from its map, so a custom `on_finished` was the only thing that ever saw both.
- Closing a rate limit group settles the hand-off its worker was in the middle of, rather than leaving it running against a scheduler that is closing at the same time. A request job the scheduler rejected or canceled before it could start left its coroutine unawaited — a `RuntimeWarning` on any run closed while requests were queued, whether or not a ceiling was set.
- The body-limit docs no longer present `concurrent_requests × max_response_body_size` as a peak. It bounds what a run holds; assembling a body into `bytes` transiently needs about twice its size, and `text()`/`json()` hold the decoded string on top.
- `AIOScraper.wait(timeout=0)` bounds the run at zero instead of falling back to `execution.timeout`, which is `None` by default and would have waited forever. It is not a poll: a run that is not already finished gets canceled and reported as `timed_out`, the same as any expired wait. `AIOScraper.result` is the read that leaves the run alone. Only an explicit `0` was affected — the config validators reject it for both `timeout` and `shutdown_timeout`.

### Changed
- **BREAKING:** a `group_by` returns a third value, the group's concurrency ceiling: `GroupBy` is now `Callable[[Request], tuple[Hashable, float, int | None]]`. `None` takes `RateLimitConfig.group_concurrency`, `0` asks for no ceiling. Return a `GroupPolicy`, which names the fields and defaults the third, or a plain tuple of the same shape.
- **BREAKING:** `add_dependencies` raises `ValueError` for a name the framework injects — `request`, `response`, `exc`, `schedule_request`, `send_request`, `pipeline` — instead of overriding it. `config` stays overridable. 0.15.0 gave the first three no warning at all and crashed each request with `TypeError: got multiple values for keyword argument`, since they are passed at the call site rather than merged in; the other three were logged and silently swapped the machinery out. The check also runs when the run starts, before anything is wired, for a name written straight into `AIOScraper.dependencies`.
- **BREAKING:** `Request` raises `ValueError` when `cb_kwargs` takes `request`, `response` or `exc`. That entry never reached the callback and crashed the request instead.
- A `cb_kwargs` entry named like a registered dependency now wins over it rather than raising `TypeError`. Callback arguments are built into one mapping instead of unpacked from three at the call, which fixes the precedence, highest to lowest: framework callback arguments > `cb_kwargs` > injected dependencies.

## 0.15.0 (2026-08-25)

### Added
- `SessionConfig.buffer_body` (`SESSION_BUFFER_BODY`) and `Request.buffer_body`, which read a response body before the callback runs. Without it the body is read inside the callback, past the retry policy: a connection dying mid-body reached the errback unretried, and the adaptive rate limiter had already recorded the request as a success at the latency of its headers. Off by default, since it holds every body in memory for the whole callback.
- `Request.url` is positional, so `Request("https://example.com", callback=parse)` works. Every other field stays keyword-only, and `Request(url=...)` is unchanged.

### Fixed
- `--concurrent-requests` and `--pending-requests` rebuild the config with `dataclasses.replace` instead of writing into the frozen one with `object.__setattr__`, so the field validators run on the override too — only the CLI's own argument parsing stood between an invalid value and the config before. A `0` is no longer dropped as falsy either: `None` is what means "not given".
- A dependency registered under a name the framework provides no longer crashes the run. `add_dependencies(schedule_request=...)` — and `send_request` before this release — raised `TypeError: got multiple values for keyword argument` from the entrypoint call, even when no entrypoint asked for it, while `config` and `pipeline` were silently overridden. All four now follow one rule: the registered value wins, and shadowing anything but `config` is logged.

### Changed
- **BREAKING:** `RateLimitConfig.enabled` is now `per_group` (`SESSION_RATE_LIMIT_PER_GROUP`). It never switched rate limiting off: `default_interval` paced every request either way, across the run instead of per group. Setting `adaptive` without it is now a `ConfigValidationError` instead of a silent no-op, since adaptive paces a group at a time.
- **BREAKING:** `RateLimitConfig.group_by` and `RequestRetryConfig.should_retry` moved to `AIOScraper(group_by=..., should_retry=...)`, joining `http_client` and `sessionmaker_factory`. A callable is the one thing no config file can hold, and with them on `Config` a third-party loader failed on the whole object rather than on those fields. Both are also plain attributes, replaceable until the run starts. `aioscraper.config.converters.parse_exception` and `parse_ssl` are public for the fields that name an object indirectly, and are what `load_config` uses.
- **BREAKING:** every config dataclass is keyword-only: `Config`, `SessionConfig`, `SchedulerConfig`, `ExecutionConfig`, `PipelineConfig`, `RequestRetryConfig`, `RateLimitConfig` and `AdaptiveRateLimitConfig`. Their field order stops being API, the way `RunResult`'s did in 0.14.0: a positional build fails instead of shifting a value onto a field added later, which is exactly what `buffer_body` would have done to `retry`.
- **DEPRECATED:** `send_request` is now `schedule_request`, and `SendRequest` is `ScheduleRequest`. The call never sent anything: it queues a request and returns as soon as it is accepted, which is what `Request.delay` and `Request.priority` act on. Both old names still resolve — the dependency is injected under either parameter name and `SendRequest` remains an alias — and are removed in 1.0.

## 0.14.0 (2026-08-25)

### Added
- A backend-neutral transport exception hierarchy: `TransportError` with `TransportTimeout`, `ConnectionFailed`, `DNSError`, `ProxyError` and `TLSError`. Every backend maps its own failures onto it, on the send and on the body read alike, keeping the original as `__cause__`. `TransportTimeout` is also a builtin `TimeoutError`.
- `TooManyRedirects` and `InvalidURL`, for a redirect chain over the limit and a URL the client refused. Both are `ClientException` but not `TransportError`, and are not retried by default.
- `RunResult.all_requests_succeeded`, true when no request ended in failure, handled by an `errback` or not; a failure a retry recovered from is not one. `ok` stays about unhandled errors.
- `RunResult.requests_retried`, attempts the retry policy admitted again. They end neither as succeeded nor as failed, so the counters now add up to `requests_started`.
- `RequestRetryConfig.max_retry_after` (`SESSION_RETRY_MAX_RETRY_AFTER`), the cap on a delay the server asked for. Still 600 seconds, and now the setting that says how long a server may park a run.
- `ExecutionConfig.max_retained_errors` (`EXECUTION_MAX_RETAINED_ERRORS`), how many exceptions `RunResult.errors` keeps. Was hard-coded at 100; the counts stay exact.
- `SESSION_MAX_RESPONSE_BODY_SIZE` accepts `0`, `none` and `unlimited` for no cap.

### Changed
- **BREAKING:** retries are enabled by default. A failing endpoint costs `attempts` extra requests per URL, and a run takes the backoff delays; `SESSION_RETRY_ENABLED=false` turns them off. Only idempotent methods are replayed, as before.
- **BREAKING:** the effective timeout — `Request.timeout`, or `session.timeout` without one — is a wall-clock budget for the whole response on every backend, raised as `TransportTimeout`. httpx and httpx2 time each phase separately, so a body arriving chunk by chunk never reached a limit: a 60s timeout allowed a download of any length. A long download now needs its own `Request.timeout`; a client passed as `http_client` gets a budget from `Request.timeout`, or from `ClientTimeout.total` when it is an `aiohttp` one and positive.
- **BREAKING:** `Response.headers` is a `multidict.CIMultiDictProxy` on every backend. `headers[name]` is the first value of a repeated header everywhere, where httpx joined them into `'a=1, b=2'`; `getall(name)` replaces httpx's `get_list(name)`.
- **BREAKING:** `SessionConfig.max_response_body_size` defaults to 32 MiB instead of `None`, which bounds memory at that times `scheduler.concurrent_requests`. A larger download needs the cap raised or set to `None`.
- **BREAKING:** `RequestRetryConfig.exceptions` defaults to `(TransportTimeout, ConnectionFailed)`. Timeouts were retried on `aiohttp` alone: `httpx.TimeoutException` is unrelated to `asyncio.TimeoutError`. `TLSError` is left out on purpose, and a timeout raised outside the transport is no longer retried.
- **BREAKING:** an `errback` and a `should_retry` hook receive the classes above, not `aiohttp.ClientError`/`httpx.HTTPError`. Catch `ClientException`, or `TransportError` for the transport failures alone.
- **BREAKING:** `Request.timeout` must be positive. `0`, a negative value, `inf` and `NaN` raise `InvalidRequestData` before dispatch.
- **BREAKING:** `RunResult` is keyword-only, so its field order is no longer API: a positional build fails instead of shifting a value onto a field added later.
- `license = "MIT"` with `license-files` (PEP 639), so the wheel carries `License-Expression` instead of the deprecated `License` field. Requires `hatchling>=1.27`.
- The compatibility policy records the two backend differences that stay: a per-request `Request.max_redirects` on `httpx`/`httpx2`, and the class raised for a body the client could not decode.

### Fixed
- A URL no parser accepts is rejected as `InvalidURL` when the request is sent, and reaches the `errback` when a middleware sets one. `yarl` used to raise a bare `ValueError` past every callback and counter.
- A numeric config value that is not finite is rejected, and a `Retry-After` header holding one is ignored. `NaN` passed every range check and parked a retry on a deadline that never comes.
- The httpx and httpx2 backends send `Request.timeout` as it is instead of testing it for truthiness, which sent a `0` to the client default.

## 0.13.0 (2026-08-17)

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
- An `auth`/`proxy_auth` `encoding` that names no codec raises `InvalidRequestData` instead of failing later inside the client.
- `--allow-partial-success`, which makes the CLI exit `0` despite recorded errors, overriding `EXECUTION_ON_ERROR`.
- `RequestRetryConfig.should_retry(request, exc, retries)`, deciding failures the `statuses`/`exceptions` match cannot express. `None` falls back to that match; the method check still applies first.
- Documentation of what the HTTP backends do differently, and of the compatibility policy: what counts as public API, and how long a deprecated one is kept.
- An `httpx2` backend for the Pydantic fork of httpx, behind the `aioscraper[httpx2]` extra. Selected with `SESSION_HTTP_BACKEND=httpx2` or by passing an `httpx2.AsyncClient` as `http_client`. Requests behave as they do on the httpx backend, the options it rejects included; `ssl=True` verifies against the trust store of the operating system, where httpx uses `certifi`.

### Changed
- **BREAKING:** the httpx backend rejects a `BasicAuth.encoding` that is not UTF-8 with `UnsupportedRequestOption` instead of ignoring it: it sends credentials as UTF-8, where aiohttp applies the field and defaults to Latin-1.
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
- Client exceptions keep their message in `args`, and survive pickling and `copy.deepcopy` with their headers and notes; both used to fail.
- On the httpx backend `Request.params` extend the query the URL already carries, as they do on aiohttp; a key present in both used to be replaced.
- The `UnsupportedRequestOption` for `Request.max_redirects` names the limit of the client in use, which is not `10` for a provided one.

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
- On SIGINT/SIGTERM in-flight work gets `execution.shutdown_timeout` to finish instead of being canceled immediately.
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
