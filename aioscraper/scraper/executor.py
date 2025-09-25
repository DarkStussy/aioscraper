import asyncio
import time
from logging import getLogger
from typing import Any

from aiojobs import Scheduler

from .request_manager import RequestManager
from ..config import Config
from .._helpers.func import get_func_kwargs
from .._helpers.asyncio import execute_coroutines
from ..pipeline.dispatcher import PipelineDispatcher
from ..session import AiohttpSession
from ..types import Scraper, Middleware, ExceptionMiddleware

logger = getLogger(__name__)


class ScraperExecutor:
    """
    Executes scrapers and manages the scraping process.

    This class is responsible for running scraper functions, managing the request
    scheduler, and handling the graceful shutdown of the scraping process.
    """

    def __init__(
        self,
        config: Config,
        scrapers: list[Scraper],
        dependencies: dict[str, Any],
        request_outer_middlewares: list[Middleware],
        request_inner_middlewares: list[Middleware],
        request_exception_middlewares: list[ExceptionMiddleware],
        response_middlewares: list[Middleware],
        pipeline_dispatcher: PipelineDispatcher,
    ) -> None:
        self._start_time: float | None = None
        self._config = config

        self._scrapers = scrapers
        self._dependencies = dependencies
        self._pipeline_dispatcher = pipeline_dispatcher

        self._scheduler = Scheduler(
            limit=self._config.scheduler.concurrent_requests,
            pending_limit=self._config.scheduler.pending_requests,
            close_timeout=self._config.scheduler.close_timeout,
        )

        self._request_queue = asyncio.PriorityQueue()
        self._request_manager = RequestManager(
            session=AiohttpSession(
                timeout=self._config.session.request.timeout,
                ssl=self._config.session.request.ssl,
            ),
            schedule_request=self._scheduler.spawn,
            queue=self._request_queue,
            delay=self._config.session.request.delay,
            shutdown_timeout=self._config.execution.shutdown_timeout,
            dependencies={"pipeline": self._pipeline_dispatcher.put_item, **self._dependencies},
            request_outer_middlewares=request_outer_middlewares,
            request_inner_middlewares=request_inner_middlewares,
            request_exception_middlewares=request_exception_middlewares,
            response_middlewares=response_middlewares,
        )

    async def run(self) -> None:
        "Start the scraping process"
        self._start_time = time.time()
        self._request_manager.listen_queue()

        scraper_kwargs = {
            "send_request": self._request_manager.sender,
            "pipeline": self._pipeline_dispatcher.put_item,
            **self._dependencies,
        }
        await asyncio.gather(*[scraper(**get_func_kwargs(scraper, scraper_kwargs)) for scraper in self._scrapers])

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
                logger.log(
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
            await execute_coroutines(
                self._scheduler.close(),
                self._request_manager.close(),
                self._pipeline_dispatcher.close(),
            )
