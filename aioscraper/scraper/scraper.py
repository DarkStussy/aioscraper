from logging import getLogger
from types import TracebackType
from typing import Type, Any

from .executor import ScraperExecutor
from ..config import Config
from ..pipeline import BasePipeline, ItemType
from ..pipeline.dispatcher import PipelineDispatcher
from ..types import Scraper, Middleware, ExceptionMiddleware, PipelineMiddleware

logger = getLogger(__name__)


class AIOScraper:
    """
    An asynchronous web scraping framework that manages multiple scrapers and their execution.

    This class provides a comprehensive solution for running multiple web scrapers concurrently,
    managing requests, handling middleware, and processing data through pipelines.

    Args:
        scrapers (list[BaseScraper]): List of scraper instances to be executed.
        config (Config | None): Configuration object. Defaults to None.
        dependencies (dict[str, Any] | None): Additional dependencies to be passed to scrapers. Defaults to None.
    """

    def __init__(
        self,
        scrapers: list[Scraper] | None = None,
        config: Config | None = None,
        dependencies: dict[str, Any] | None = None,
    ) -> None:
        self._start_time: float | None = None
        self._config = config or Config()

        self._scrapers = scrapers or []
        self._dependencies = dependencies or {}

        self._request_outer_middlewares: list[Middleware] = []
        self._request_inner_middlewares: list[Middleware] = []
        self._request_exception_middlewares: list[ExceptionMiddleware] = []
        self._response_middlewares: list[Middleware] = []

        self._pipelines: dict[str, list[BasePipeline[Any]]] = {}
        self._pipeline_dispatcher = PipelineDispatcher(self._pipelines)

        self._executor: ScraperExecutor | None = None

    def register(self, scraper: Scraper) -> Scraper:
        "Register a scraper"
        self._scrapers.append(scraper)
        return scraper

    def add_pipeline(self, name: str, pipeline: BasePipeline[ItemType]) -> None:
        """
        Add a pipeline to process scraped data.

        Args:
            name (str): Name identifier for the pipeline.
            pipeline (BasePipeline): Pipeline instance to be added.
        """
        if name not in self._pipelines:
            self._pipelines[name] = [pipeline]
        else:
            self._pipelines[name].append(pipeline)

    def add_pipeline_pre_processing_middlewares(self, *middlewares: PipelineMiddleware) -> None:
        """
        Add pipeline pre-processing middlewares.

        These middlewares are executed before processing an item in the pipeline.
        """
        self._pipeline_dispatcher.add_pre_processing_middlewares(*middlewares)

    def add_pipeline_post_processing_middlewares(self, *middlewares: PipelineMiddleware) -> None:
        """
        Add pipeline post-processing middlewares.

        These middlewares are executed after processing an item in the pipeline.
        """
        self._pipeline_dispatcher.add_post_processing_middlewares(*middlewares)

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

    def add_request_exception_middlewares(self, *middlewares: ExceptionMiddleware) -> None:
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

    async def start(self) -> None:
        self._executor = ScraperExecutor(
            config=self._config,
            scrapers=self._scrapers,
            dependencies=self._dependencies,
            request_outer_middlewares=self._request_outer_middlewares,
            request_inner_middlewares=self._request_inner_middlewares,
            request_exception_middlewares=self._request_exception_middlewares,
            response_middlewares=self._response_middlewares,
            pipeline_dispatcher=self._pipeline_dispatcher,
        )
        await self._executor.run()

    async def close(self) -> None:
        if self._executor is not None:
            await self._executor.close()
