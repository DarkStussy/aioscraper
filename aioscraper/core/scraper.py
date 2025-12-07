from contextlib import AsyncExitStack, asynccontextmanager
from logging import getLogger
from types import TracebackType
from typing import AsyncIterator, Callable, Self, Type, Any

from .executor import ScraperExecutor
from .pipeline import PipelineDispatcher
from ..config import Config, load_config
from ..holders import MiddlewareHolder, PipelineHolder
from ..types import Scraper
from ..session import SessionMakerFactory, get_sessionmaker

logger = getLogger(__name__)

Lifespan = Callable[["AIOScraper"], AsyncIterator[None]]


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
            :func:`aioscraper.session.factory.get_sessionmaker`).
    """

    def __init__(
        self,
        *scrapers: Scraper,
        config: Config | None = None,
        lifespan: Lifespan | None = None,
        sessionmaker_factory: SessionMakerFactory | None = None,
    ):
        self.scrapers = [*scrapers]
        self.config = config
        self.dependencies: dict[str, Any] = {}

        self._sessionmaker_factory = sessionmaker_factory or get_sessionmaker

        @asynccontextmanager
        async def default_lifespan(_: Self):
            yield

        self._lifespan = asynccontextmanager(lifespan) if lifespan is not None else default_lifespan
        self._lifespan_exit_stack = AsyncExitStack()

        self._middleware_holder = MiddlewareHolder()
        self._pipeline_holder = PipelineHolder()

        self._executor: ScraperExecutor | None = None

    def __call__(self, scraper: Scraper) -> Scraper:
        "Add a scraper callable and return it for decorator use."
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
    def middleware(self) -> MiddlewareHolder:
        "Access the middleware registry for request/response hooks."
        return self._middleware_holder

    @property
    def pipeline(self) -> PipelineHolder:
        "Access the pipeline registry and middleware helpers."
        return self._pipeline_holder

    async def __aenter__(self) -> Self:
        await self._lifespan_exit_stack.enter_async_context(self._lifespan(self))
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ):
        try:
            await self.close()
        finally:
            await self._lifespan_exit_stack.__aexit__(exc_type, exc_val, exc_tb)

    async def start(self):
        """Initialize and run the scraper with the configured settings."""
        config = self.config or load_config()
        self._executor = ScraperExecutor(
            config=config,
            scrapers=self.scrapers,
            dependencies=self.dependencies,
            middleware_holder=self._middleware_holder,
            pipeline_dispatcher=PipelineDispatcher(
                config.pipeline,
                pipelines=self._pipeline_holder.pipelines,
                global_middlewares=self._pipeline_holder.global_middlewares,
                dependencies=self.dependencies,
            ),
            sessionmaker=self._sessionmaker_factory(config),
        )
        await self._executor.run()

    async def close(self):
        "Close the scraper and its associated resources."
        if self._executor is not None:
            await self._executor.close()
