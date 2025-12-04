from logging import getLogger
from types import TracebackType
from typing import Type, Any

from .executor import ScraperExecutor
from ..config import Config
from ..pipeline import BasePipeline
from ..pipeline.dispatcher import PipelineContainer, PipelineDispatcher
from ..types import Scraper, Middleware, PipelineMiddleware, ItemType

logger = getLogger(__name__)


class AIOScraper:
    """
    An asynchronous web scraping framework that manages multiple scrapers and their execution.

    This class provides a comprehensive solution for running multiple web scrapers concurrently,
    managing requests, handling middleware, and processing data through pipelines.

    Args:
        scrapers (tuple[BaseScraper, ...]): List of scraper instances to be executed
    """

    def __init__(self, *scrapers: Scraper) -> None:
        self._scrapers = [*scrapers]
        self._dependencies: dict[str, Any] = {}

        self._request_outer_middlewares: list[Middleware] = []
        self._request_inner_middlewares: list[Middleware] = []
        self._request_exception_middlewares: list[Middleware] = []
        self._response_middlewares: list[Middleware] = []

        self._pipeline_containers: dict[str, PipelineContainer] = {}

        self._executor: ScraperExecutor | None = None

    def register(self, scraper: Scraper) -> Scraper:
        "Register a single scraper callable; returns it for decorator usage."
        self._scrapers.append(scraper)
        return scraper

    def register_all(self, *scrapers: Scraper) -> None:
        "Register multiple scraper callables at once."
        self._scrapers.extend(scrapers)

    def register_dependencies(self, **kwargs: Any) -> None:
        "Register shared dependencies to inject into scraper callbacks."
        self._dependencies.update(kwargs)

    def add_pipelines(self, name: str, *pipelines: BasePipeline[ItemType]) -> None:
        """
        Add pipelines to process scraped data.

        Args:
            name (str): Name identifier for the pipeline
            pipelines (tuple[BasePipeline[ItemType], ...]): Pipeline instances to be added
        """
        if name not in self._pipeline_containers:
            self._pipeline_containers[name] = PipelineContainer(pipelines=[*pipelines])
        else:
            self._pipeline_containers[name].pipelines.extend(pipelines)

    def add_pipeline_pre_middlewares(self, name: str, *middlewares: PipelineMiddleware[ItemType]) -> None:
        """
        Add pipeline pre-processing middlewares.

        These middlewares are executed before processing an item in the pipeline.
        """
        if name not in self._pipeline_containers:
            self._pipeline_containers[name] = PipelineContainer(pre_middlewares=[*middlewares])
        else:
            self._pipeline_containers[name].pre_middlewares.extend(middlewares)

    def add_pipeline_post_middlewares(self, name: str, *middlewares: PipelineMiddleware[ItemType]) -> None:
        """
        Add pipeline post-processing middlewares.

        These middlewares are executed after processing an item in the pipeline.
        """
        if name not in self._pipeline_containers:
            self._pipeline_containers[name] = PipelineContainer(post_middlewares=[*middlewares])
        else:
            self._pipeline_containers[name].post_middlewares.extend(middlewares)

    def add_outer_request_middlewares(self, *middlewares: Middleware) -> None:
        """
        Add outer request middlewares.

        These middlewares are executed before the request is sent to the scheduler.
        """
        self._request_outer_middlewares.extend(middlewares)

    def add_inner_request_middlewares(self, *middlewares: Middleware) -> None:
        """
        Add inner request middlewares.

        These middlewares are executed after the request is scheduled but before it is sent.
        """
        self._request_inner_middlewares.extend(middlewares)

    def add_request_exception_middlewares(self, *middlewares: Middleware) -> None:
        """
        Add request exception middlewares.

        These middlewares are executed when an exception occurs during the request processing.
        """
        self._request_exception_middlewares.extend(middlewares)

    def add_response_middlewares(self, *middlewares: Middleware) -> None:
        """
        Add response middlewares.

        These middlewares are executed after receiving the response.
        """
        self._response_middlewares.extend(middlewares)

    async def __aenter__(self) -> "AIOScraper":
        return self

    async def __aexit__(
        self,
        exc_type: Type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.close()

    async def start(self, config: Config | None = None) -> None:
        """
        Initialize and run the scraper with the given configuration.

        Args:
            config (Config | None): Optional configuration; falls back to defaults when not provided.
        """
        config = config or Config()
        self._executor = ScraperExecutor(
            config=config,
            scrapers=self._scrapers,
            dependencies=self._dependencies,
            request_outer_middlewares=self._request_outer_middlewares,
            request_inner_middlewares=self._request_inner_middlewares,
            request_exception_middlewares=self._request_exception_middlewares,
            response_middlewares=self._response_middlewares,
            pipeline_dispatcher=PipelineDispatcher(config.pipeline, self._pipeline_containers),
        )
        await self._executor.run()

    async def close(self) -> None:
        if self._executor is not None:
            await self._executor.close()
