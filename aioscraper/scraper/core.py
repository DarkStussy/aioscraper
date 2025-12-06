from contextlib import AsyncExitStack, asynccontextmanager
from logging import getLogger
from types import TracebackType
from typing import AsyncIterator, Callable, Self, Type, Any

from .executor import ScraperExecutor
from ..config import Config
from ..holders import MiddlewareHolder, PipelineHolder
from ..pipeline.dispatcher import PipelineDispatcher
from ..types import Scraper
from ..session import BaseSession, get_session

logger = getLogger(__name__)

Lifespan = Callable[["AIOScraper"], AsyncIterator[None]]


class AIOScraper:
    """
    An asynchronous web scraping framework that manages multiple scrapers and their execution.

    This class provides a comprehensive solution for running multiple web scrapers concurrently,
    managing requests, handling middleware, and processing data through pipelines.

    Args:
        scrapers (tuple[Scraper, ...]): List of scraper callables to execute
    """

    def __init__(self, *scrapers: Scraper) -> None:
        self.scrapers = [*scrapers]
        self.dependencies: dict[str, Any] = {}

        @asynccontextmanager
        async def default_lifespan(_: Self):
            yield

        self._lifespan = default_lifespan
        self._lifespan_exit_stack = AsyncExitStack()

        self._middleware_holder = MiddlewareHolder()
        self._pipeline_holder = PipelineHolder()

        self._executor: ScraperExecutor | None = None

    def __call__(self, scraper: Scraper) -> Scraper:
        "Add a scraper callable and return it for decorator use."
        self.scrapers.append(scraper)
        return scraper

    def add_dependencies(self, **kwargs: Any) -> None:
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
    ) -> None:
        try:
            await self.close()
        finally:
            await self._lifespan_exit_stack.__aexit__(exc_type, exc_val, exc_tb)

    def _create_session(self, config: Config) -> BaseSession:
        return get_session(config)

    async def start(self, config: Config | None = None) -> None:
        """
        Initialize and run the scraper with the given configuration.

        Args:
            config (Config | None): Optional configuration; falls back to defaults when not provided.
        """
        config = config or Config()
        self._executor = ScraperExecutor(
            config=config,
            scrapers=self.scrapers,
            dependencies=self.dependencies,
            middleware_holder=self._middleware_holder,
            pipeline_dispatcher=PipelineDispatcher(config.pipeline, self._pipeline_holder.pipelines),
            session=self._create_session(config),
        )
        await self._executor.run()

    async def close(self) -> None:
        "Close the scraper and its associated resources."
        if self._executor is not None:
            await self._executor.close()
