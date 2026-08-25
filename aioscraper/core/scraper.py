import asyncio
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from enum import Enum, auto
from functools import partial
from logging import getLogger
from types import TracebackType
from typing import Any, AsyncGenerator, Callable, Mapping, Self

from aioscraper._helpers.deps import RESERVED_DEPENDENCIES, reject_reserved
from aioscraper._helpers.log import get_log_name
from aioscraper.config import Config, load_config
from aioscraper.holders import MiddlewareHolder, PipelineHolder
from aioscraper.types import GroupBy, Scraper, ShouldRetry

from .errors import ErrorCollector, RunResult, ScraperError
from .executor import ScraperExecutor
from .pipeline import PipelineDispatcher
from .session import HttpClient, SessionMakerFactory, get_sessionmaker
from .stats import RunStats

logger = getLogger(__name__)

Lifespan = Callable[["AIOScraper"], AsyncGenerator[None, None]]


class _State(Enum):
    """Lifecycle position of an :class:`AIOScraper`.

    Attributes:
        CREATED: Configured, never started.
        STARTING: ``__aenter__`` reserved the instance and is setting the lifespan up.
        RUNNING: The background task exists; it may still be running or already finished.
        CLOSING: Teardown is in progress.
        CLOSED: Teardown finished, terminal.
    """

    CREATED = auto()
    STARTING = auto()
    RUNNING = auto()
    CLOSING = auto()
    CLOSED = auto()


class AIOScraper:
    """Core entrypoint that wires scrapers, middlewares, and pipelines.

    An instance is single-use: :meth:`start` and ``async with`` raise ``RuntimeError`` on a second
    run, because closing it closes the executor and its sessions and neither is rebuilt. A finished
    run stays readable through :attr:`errors`; scraping again takes a new instance.

    Args:
        *scrapers (Scraper): Callable scrapers queued on startup.
        config (Config | None): Pre-built configuration; when ``None`` one is
            built with :func:`load_config`.
        lifespan (Lifespan | None): Optional async context manager factory
            that wraps the scraper's lifecycle (setup/teardown).
        http_client (ClientSession | AsyncClient | None): Send through this
            ``aiohttp``/``httpx`` client instead of creating one. It selects the
            backend, is used as configured, and stays open when the run ends.
        sessionmaker_factory (SessionMakerFactory | None): Override the
            function that builds HTTP sessions (defaults to
            :func:`aioscraper.core.session.factory.get_sessionmaker`).
            Mutually exclusive with ``http_client``.
        group_by (GroupBy | None): Maps a request to its rate limit group key and that group's
            interval in seconds; ``None`` groups by hostname at
            :attr:`RateLimitConfig.default_interval <aioscraper.config.models.RateLimitConfig>`.
        should_retry (ShouldRetry | None): Decides a failure the retry config's
            ``statuses``/``exceptions`` cannot express, such as a marker in the error body;
            ``None`` defers to that match, and the method check applies first.

    Raises:
        ValueError: Both ``http_client`` and ``sessionmaker_factory`` are given.
    """

    def __init__(
        self,
        *scrapers: Scraper,
        config: Config | None = None,
        lifespan: Lifespan | None = None,
        http_client: HttpClient | None = None,
        sessionmaker_factory: SessionMakerFactory | None = None,
        group_by: GroupBy | None = None,
        should_retry: ShouldRetry | None = None,
    ):
        if http_client is not None and sessionmaker_factory is not None:
            raise ValueError("http_client and sessionmaker_factory are mutually exclusive")

        self.scrapers = [*scrapers]
        self.config = config or load_config()
        self.group_by = group_by
        self.should_retry = should_retry
        self.dependencies: dict[str, Any] = {}
        self._error_collector = ErrorCollector()
        self._stats = RunStats()

        self._sessionmaker_factory = sessionmaker_factory or partial(get_sessionmaker, client=http_client)

        @asynccontextmanager
        async def default_lifespan(_: Self):
            yield

        self._lifespan = asynccontextmanager(lifespan) if lifespan is not None else default_lifespan
        self._lifespan_exit_stack = AsyncExitStack()

        self._middleware_holder = MiddlewareHolder()
        self._pipeline_holder = PipelineHolder()

        self._task: asyncio.Task[None] | None = None
        self._state = _State.CREATED
        self._timed_out = False
        self._closed = asyncio.Event()
        self._lifecycle = asyncio.Lock()

    def __call__(self, scraper: Scraper) -> Scraper:
        "Add a scraper callable and return it for decorator use."
        logger.debug("Adding scraper %s", get_log_name(scraper))
        self.scrapers.append(scraper)
        return scraper

    def add_dependencies(self, **kwargs: Any):
        """Register objects injected by parameter name into scrapers, callbacks, errbacks and
        middleware factories. A pipeline gets what its own constructor was given, nothing more.

        Raises:
            ValueError: A name is one the framework injects. Only ``config`` may be replaced.
        """
        reject_reserved(kwargs, RESERVED_DEPENDENCIES, "Dependency names")
        self.dependencies.update(kwargs)

    def lifespan(self, lifespan: Lifespan) -> Lifespan:
        "Attach an async generator that sets the run up before its ``yield`` and tears it down after."
        self._lifespan = asynccontextmanager(lifespan)
        return lifespan

    @property
    def errors(self) -> tuple[ScraperError, ...]:
        """Errors that were logged and swallowed during the run.

        Capped at the collector's retention limit; use :attr:`error_counts` for exact totals.

        Returns:
            tuple[ScraperError, ...]: The most recent unhandled request and resource-close failures.
        """
        return self._error_collector.errors

    @property
    def error_counts(self) -> Mapping[str, int]:
        """Exact number of swallowed errors per context.

        Returns:
            Mapping[str, int]: Error count keyed by context, e.g. ``{"request": 12}``.
        """
        return self._error_collector.counts

    @property
    def middleware(self) -> MiddlewareHolder:
        "The request middleware registry; call it as a decorator to register a factory."
        return self._middleware_holder

    @property
    def pipeline(self) -> PipelineHolder:
        "The pipeline registry, and the decorators for pipeline middlewares."
        return self._pipeline_holder

    async def __aenter__(self) -> Self:
        # reserved before the first await, so two concurrent entries cannot both set the lifespan up
        self._reject_rerun()
        self._state = _State.STARTING
        # the lock is for close() alone: STARTING already rejects start() and another entry, but
        # close() would otherwise finish the instance while the lifespan is still setting it up
        async with self._lifecycle:
            try:
                await self._lifespan_exit_stack.enter_async_context(self._lifespan(self))
                self._start()
            except BaseException:
                # nothing is left running, so the failed entry does not consume the single use
                self._state = _State.CREATED
                await self._lifespan_exit_stack.aclose()
                raise

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ):
        try:
            await self.close()
        finally:
            await self._lifespan_exit_stack.__aexit__(exc_type, exc_val, exc_tb)

    def _reject_rerun(self):
        if self._state is not _State.CREATED:
            raise RuntimeError(f"AIOScraper is single-use and is already {self._state.name.lower()}; create a new one")

    def _require_started(self) -> asyncio.Task[None]:
        if self._task is None:
            raise RuntimeError("AIOScraper was not started: call start() or use it as an async context manager")

        return self._task

    def start(self):
        """Start the scraper and run it in the background.

        Raises:
            RuntimeError: The instance was already started or closed, or there is no running
                event loop. The latter leaves it startable.
        """
        self._reject_rerun()
        self._start()

    def _start(self):
        # the state moves only once the task exists: a create_task that raises leaves the instance
        # startable, with the coroutine it never took closed
        run = self._run()
        try:
            task = asyncio.create_task(run)
        except BaseException:
            run.close()
            raise

        self._task = task
        self._state = _State.RUNNING

    async def _run(self):
        # before anything is wired: the pipeline middleware factories are handed the same mapping
        reject_reserved(self.dependencies, RESERVED_DEPENDENCIES, "Dependency names")
        # built here rather than in __init__: the config can still be replaced until the run starts
        self._error_collector = ErrorCollector(self.config.execution.max_retained_errors)
        executor = ScraperExecutor(
            config=self.config,
            scrapers=self.scrapers,
            dependencies=self.dependencies,
            middleware_holder=self._middleware_holder,
            pipeline_dispatcher=PipelineDispatcher(
                self.config.pipeline,
                pipelines=self._pipeline_holder.pipelines,
                global_middleware_factories=self._pipeline_holder.global_middleware_factories,
                dependencies=self.dependencies,
                error_collector=self._error_collector,
                stats=self._stats,
            ),
            sessionmaker=self._sessionmaker_factory(self.config.session),
            error_collector=self._error_collector,
            stats=self._stats,
            group_by=self.group_by,
            should_retry=self.should_retry,
        )
        try:
            logger.debug("Starting executor")
            await executor.run()
            logger.debug("Scraper execution completed successfully")
        finally:
            logger.debug("Closing executor resources")
            await executor.close()

    async def shutdown(self) -> RunResult:
        """Trigger a graceful shutdown of the scraper.

        Returns:
            RunResult: What the run recorded before it was shut down.

        Raises:
            RuntimeError: The scraper was never started.
        """
        self._require_started()
        if self._state is not _State.RUNNING:
            return await self._closed_result()

        logger.debug("Initiating graceful shutdown (timeout=%0.10gs)", self.config.execution.shutdown_timeout)
        try:
            return await self.wait(timeout=self.config.execution.shutdown_timeout)
        finally:
            await self.close()

    async def wait(self, timeout: float | None = None) -> RunResult:
        """Wait for the scraper to finish.

        On a closing or closed scraper the call waits for teardown instead, so the result covers
        the errors it recorded. A ``close()`` landing mid-wait is reported the same way rather
        than canceling the caller.

        Args:
            timeout (float | None): Overrides ``execution.timeout`` for this call; ``None`` takes
                it, and ``0`` checks without waiting. It bounds the run, not teardown.

        Returns:
            RunResult: What the run recorded, including whether the timeout expired.

        Raises:
            RuntimeError: The scraper was never started.
        """
        task = self._require_started()
        if self._state is not _State.RUNNING:
            return await self._closed_result()

        log_level = self.config.execution.log_level
        if timeout is None:
            timeout = self.config.execution.timeout

        logger.debug("Waiting for scraper to finish (timeout=%ss)", timeout)
        # watching the task rather than awaiting it: a close() that cancels the run must not
        # cancel this call too
        done, _ = await asyncio.wait((task,), timeout=timeout)
        if not done:
            logger.log(log_level, "wait timeout exceeded (%ss) - forcing shutdown", timeout)
            self._timed_out = True
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        elif not task.cancelled():
            # asyncio.wait does not surface the task's exception, so raise what the run failed with
            task.result()

        if self._state is not _State.RUNNING:
            return await self._closed_result()

        return self._result()

    @property
    def result(self) -> RunResult:
        """The outcome as it stands.

        Returns:
            RunResult: Errors and counters recorded so far. ``interrupted`` is set by the runner.
        """
        return self._result()

    def _result(self) -> RunResult:
        # the timeout is a property of the run, not of the call: every later result keeps it
        return RunResult(
            errors=self.errors,
            error_counts=self.error_counts,
            timed_out=self._timed_out,
            requests_started=self._stats.requests_started,
            requests_succeeded=self._stats.requests_succeeded,
            requests_failed=self._stats.requests_failed,
            requests_retried=self._stats.requests_retried,
            items_processed=self._stats.items_processed,
        )

    async def _closed_result(self) -> RunResult:
        "Report the run once teardown is over: closing the executor records errors of its own."
        await self._closed.wait()
        return self._result()

    async def close(self):
        """Close the scraper and its associated resources; the instance cannot run again.

        Concurrent calls wait for the teardown started by the first one, and a call landing while
        the scraper is starting waits for the startup to settle before tearing it down.
        """
        if self._state is _State.CLOSED:
            return

        async with self._lifecycle:
            if self._state is _State.CLOSED:
                return

            self._state = _State.CLOSING
            try:
                if self._task is not None:
                    self._task.cancel()
                    with suppress(asyncio.CancelledError):
                        await self._task
            finally:
                self._state = _State.CLOSED
                self._closed.set()
