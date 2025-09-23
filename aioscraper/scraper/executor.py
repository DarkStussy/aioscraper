import asyncio
import time
from logging import Logger, getLogger
from types import TracebackType
from typing import Type, Any

from aiojobs import Scheduler

from .base import BaseScraper

from .request_manager import RequestManager
from ..config import Config
from .._helpers.func import get_func_kwargs
from .._helpers.asyncio import execute_coroutines
from ..pipeline import BasePipeline, ItemType
from ..pipeline.dispatcher import PipelineDispatcher
from ..session import AiohttpSession
from ..types import Middleware, ExceptionMiddleware


class AIOScraper:
    """
    An asynchronous web scraping framework that manages multiple scrapers and their execution.

    This class provides a comprehensive solution for running multiple web scrapers concurrently,
    managing requests, handling middleware, and processing data through pipelines.

    Args:
        scrapers (list[BaseScraper]): List of scraper instances to be executed.
        config (Config | None): Configuration object. Defaults to None.
        dependencies (dict[str, Any] | None): Additional dependencies to be passed to scrapers. Defaults to None.
        logger (Logger | None): Logger instance. Defaults to None.
    """

    def __init__(
        self,
        scrapers: list[BaseScraper],
        config: Config | None = None,
        dependencies: dict[str, Any] | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._start_time: float | None = None
        self._config = config or Config()
        self._logger = logger or getLogger("aioscraper")

        self._scrapers = scrapers
        self._request_outer_middlewares: list[Middleware] = []
        self._request_inner_middlewares: list[Middleware] = []
        self._request_exception_middlewares: list[ExceptionMiddleware] = []
        self._response_middlewares: list[Middleware] = []

        self._pipelines: dict[str, list[BasePipeline[Any]]] = {}
        self._pipeline_dispatcher = PipelineDispatcher(self._logger.getChild("pipeline"), pipelines=self._pipelines)

        self._dependencies = dependencies or {}

        def _exception_handler(_: Scheduler, context: dict[str, Any]):
            if "job" in context:
                self._logger.error(f'{context["message"]}: {context["exception"]}', extra={"context": context})
            else:
                self._logger.error("Unhandled error", extra={"context": context})

        self._scheduler = Scheduler(
            limit=self._config.scheduler.concurrent_requests,
            pending_limit=self._config.scheduler.pending_requests,
            close_timeout=self._config.scheduler.close_timeout,
            exception_handler=_exception_handler,
        )

        self._request_queue = asyncio.PriorityQueue()
        self._request_manager = RequestManager(
            logger=self._logger.getChild("request_worker"),
            session=AiohttpSession(
                timeout=self._config.session.request.timeout,
                ssl=self._config.session.request.ssl,
            ),
            schedule_request=self._scheduler.spawn,
            queue=self._request_queue,
            delay=self._config.session.request.delay,
            shutdown_timeout=self._config.execution.shutdown_timeout,
            dependencies={"pipeline": self._pipeline_dispatcher.put_item, **self._dependencies},
            request_outer_middlewares=self._request_outer_middlewares,
            request_inner_middlewares=self._request_inner_middlewares,
            request_exception_middlewares=self._request_exception_middlewares,
            response_middlewares=self._response_middlewares,
        )

        self._all_dependencies: dict[str, Any] = {
            "logger": self._logger,
            "send_request": self._request_manager.sender,
            "pipeline": self._pipeline_dispatcher.put_item,
            **self._dependencies,
        }

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
        "Start the scraping process"
        self._start_time = time.time()
        self._request_manager.listen_queue()

        await asyncio.gather(
            *[scraper.start(**get_func_kwargs(scraper.start, self._all_dependencies)) for scraper in self._scrapers]
        )

    async def _shutdown(self) -> bool:
        "Internal method to handle graceful shutdown of the scraper"
        status = False

        if self._start_time is None:
            return status

        execution_timeout = (
            max(self._config.execution.timeout - (time.time() - self._start_time), 0.1)
            if self._config.execution.timeout
            else None
        )
        while True:
            if execution_timeout is not None and time.time() - self._start_time > execution_timeout:
                self._logger.log(
                    level=self._config.execution.log_level,
                    msg=f"execution timeout: {self._config.execution.timeout}",
                )
                status = True
                break
            if len(self._scheduler) == 0 and self._request_queue.qsize() == 0:
                break

            await asyncio.sleep(self._config.execution.shutdown_check_interval)

        return status

    async def shutdown(self) -> None:
        "Initiate the shutdown process for the scraper"
        force = await self._shutdown()
        await self._request_manager.shutdown(force)

    async def close(self, shutdown: bool = True) -> None:
        """
        Close all resources and cleanup.

        Args:
            shutdown (bool, optional): Whether to perform shutdown before closing. Defaults to True.
        """
        try:
            await self.shutdown() if shutdown else await self._request_manager.shutdown(force=True)
        finally:
            scraper_kwargs = {"pipeline": self._pipeline_dispatcher.put_item, **self._dependencies}
            await execute_coroutines(
                self._logger,
                *[scraper.close(**get_func_kwargs(scraper.close, scraper_kwargs)) for scraper in self._scrapers],
            )

            await execute_coroutines(
                self._logger,
                self._scheduler.close(),
                self._request_manager.close(),
                self._pipeline_dispatcher.close(),
            )
