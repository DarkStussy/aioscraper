import asyncio
from contextlib import AsyncExitStack, asynccontextmanager, suppress
from logging import getLogger
from types import TracebackType
from typing import Any, AsyncGenerator, Callable, Mapping, Self

from aioscraper._helpers.log import get_log_name
from aioscraper.config import Config, load_config
from aioscraper.holders import MiddlewareHolder, PipelineHolder
from aioscraper.types import Scraper

from .errors import ErrorCollector, RunResult, ScraperError
from .executor import ScraperExecutor
from .pipeline import PipelineDispatcher
from .session import SessionMakerFactory, get_sessionmaker

logger = getLogger(__name__)

Lifespan = Callable[["AIOScraper"], AsyncGenerator[None, None]]


class AIOScraper:
    """Core entrypoint that wires scrapers, middlewares, and pipelines.

    Args:
        *scrapers (Scraper): Callable scrapers queued on startup.
        config (Config | None): Pre-built configuration; when ``None`` the
            scraper loads one lazily via :func:`load_config` on ``start``.
        lifespan (Lifespan | None): Optional async context manager factory
            that wraps the scraper's lifecycle (setup/teardown).
        sessionmaker_factory (SessionMakerFactory | None): Override the
            function that builds HTTP sessions (defaults to
            :func:`aioscraper.core.session.factory.get_sessionmaker`).
    """

    def __init__(
        self,
        *scrapers: Scraper,
        config: Config | None = None,
        lifespan: Lifespan | None = None,
        sessionmaker_factory: SessionMakerFactory | None = None,
    ):
        self.scrapers = [*scrapers]
        self.config = config or load_config()
        self.dependencies: dict[str, Any] = {}
        self._error_collector = ErrorCollector()

        self._sessionmaker_factory = sessionmaker_factory or get_sessionmaker

        @asynccontextmanager
        async def default_lifespan(_: Self):
            yield

        self._lifespan = asynccontextmanager(lifespan) if lifespan is not None else default_lifespan
        self._lifespan_exit_stack = AsyncExitStack()

        self._middleware_holder = MiddlewareHolder()
        self._pipeline_holder = PipelineHolder()

        self._task: asyncio.Task[None] | None = None

    def __call__(self, scraper: Scraper) -> Scraper:
        "Add a scraper callable and return it for decorator use."
        logger.debug("Adding scraper %s", get_log_name(scraper))
        self.scrapers.append(scraper)
        return scraper

    def add_dependencies(self, **kwargs: Any):
        "Add shared dependencies to inject into scraper callbacks."
        self.dependencies.update(kwargs)

    def lifespan(self, lifespan: Lifespan) -> Lifespan:
        "Attach a lifespan callback to run before/after scraping."
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
        "Access the middleware registry for request/response hooks."
        return self._middleware_holder

    @property
    def pipeline(self) -> PipelineHolder:
        "Access the pipeline registry and middleware helpers."
        return self._pipeline_holder

    async def __aenter__(self) -> Self:
        await self._lifespan_exit_stack.enter_async_context(self._lifespan(self))
        self.start()
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

    def start(self):
        "Start the scraper and run it in the background."
        if self._task is None:
            self._task = asyncio.create_task(self._run())

    async def _run(self):
        """Initialize and run the scraper with the configured settings."""
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
            ),
            sessionmaker=self._sessionmaker_factory(self.config.session),
            error_collector=self._error_collector,
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
        """
        if self._task is None:
            logger.debug("Shutdown called but scraper is not running")
            return self._result()

        logger.debug("Initiating graceful shutdown (timeout=%0.10gs)", self.config.execution.shutdown_timeout)
        try:
            return await self.wait(timeout=self.config.execution.shutdown_timeout)
        finally:
            await self.close()

    async def wait(self, timeout: float | None = None) -> RunResult:  # noqa: ASYNC109
        """Wait for the scraper to finish.

        Args:
            timeout (float | None): Overrides ``execution.timeout`` for this call.

        Returns:
            RunResult: What the run recorded, including whether the timeout expired.
        """
        if self._task is None:
            logger.debug("Wait called but scraper is not running")
            return self._result()

        log_level = self.config.execution.log_level
        timeout = timeout or self.config.execution.timeout

        logger.debug("Waiting for scraper to finish (timeout=%ss)", timeout)
        try:
            await asyncio.wait_for(self._task, timeout=timeout)
        except asyncio.TimeoutError:
            logger.log(log_level, "wait timeout exceeded (%ss) - forcing shutdown", timeout)
            return self._result(timed_out=True)

        return self._result()

    def _result(self, *, timed_out: bool = False) -> RunResult:
        return RunResult(errors=self.errors, error_counts=self.error_counts, timed_out=timed_out)

    async def close(self):
        "Close the scraper and its associated resources."
        if self._task is None:
            logger.debug("Close called but scraper is not running")
            return

        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
