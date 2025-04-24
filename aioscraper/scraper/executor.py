import asyncio
import time
from logging import Logger, getLogger
from types import TracebackType
from typing import Type, Any

from aiojobs import Scheduler

from .base import BaseScraper

from .request_manager import RequestManager
from ..config import Config
from ..helpers import get_func_kwargs
from ..pipeline import BasePipeline
from ..pipeline.dispatcher import PipelineDispatcher
from ..session.aiohttp import AiohttpSession
from ..types import RequestMiddleware, ResponseMiddleware


class AIOScraper:
    """
    An asynchronous web scraping framework that manages multiple scrapers and their execution.

    This class provides a comprehensive solution for running multiple web scrapers concurrently,
    managing requests, handling middleware, and processing data through pipelines.

    Args:
        scraper (list[BasesScraper]): List of scraper instances to be executed.
        config (Config | None): Configuration object. Defaults to None.
        logger (Logger | None): Logger instance. Defaults to None.
    """

    def __init__(
        self,
        scrapers: list[BaseScraper],
        config: Config | None = None,
        logger: Logger | None = None,
    ) -> None:
        self._start_time = time.time()
        self._config = config or Config()
        self._logger = logger or getLogger("aioscraper")

        self._scrapers = scrapers
        self._request_outer_middlewares = []
        self._request_inner_middlewares = []
        self._response_middlewares = []

        self._pipelines: dict[str, list[BasePipeline]] = {}
        self._pipeline_dispatcher = PipelineDispatcher(self._logger.getChild("pipeline"), pipelines=self._pipelines)

        def _exception_handler(_, context: dict[str, Any]):
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
            srv_kwargs={"pipeline": self._pipeline_dispatcher.put_item},
            request_outer_middlewares=self._request_outer_middlewares,
            request_inner_middlewares=self._request_inner_middlewares,
            response_middlewares=self._response_middlewares,
        )

    def add_pipeline(self, name: str, pipeline: BasePipeline) -> None:
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

    def add_outer_request_middlewares(self, *middlewares: RequestMiddleware) -> None:
        """
        Add outer request middlewares.

        These middlewares are executed before the request is sent to the scheduler.
        """
        self._request_outer_middlewares.extend(middlewares)

    def add_inner_request_middlewares(self, *middlewares: RequestMiddleware) -> None:
        """
        Add inner request middlewares.

        These middlewares are executed after the request is scheduled but before it is sent.
        """
        self._request_inner_middlewares.extend(middlewares)

    def add_response_middlewares(self, *middlewares: ResponseMiddleware) -> None:
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
        await self._pipeline_dispatcher.initialize()
        self._request_manager.listen_queue()

        scraper_args = {"send_request": self._request_manager.sender, "pipeline": self._pipeline_dispatcher.put_item}
        for scraper in self._scrapers:
            await scraper.initialize(**get_func_kwargs(scraper.initialize, scraper_args))

        await asyncio.gather(
            *[scraper.start(**get_func_kwargs(scraper.start, scraper_args)) for scraper in self._scrapers]
        )

    async def _shutdown(self) -> bool:
        "Internal method to handle graceful shutdown of the scraper"
        status = False
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
        if shutdown:
            await self.shutdown()

        scraper_args = {"pipeline": self._pipeline_dispatcher.put_item}
        try:
            for scraper in self._scrapers:
                await scraper.close(**get_func_kwargs(scraper.close, scraper_args))
        finally:
            await self._scheduler.close()
            await self._request_manager.close()
            await self._pipeline_dispatcher.close()
