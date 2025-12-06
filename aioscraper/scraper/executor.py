import asyncio
import time
from logging import getLogger
from typing import Any

from aiojobs import Scheduler

from .request_manager import RequestManager
from .pipeline import PipelineDispatcher
from ..config import Config
from ..holders import MiddlewareHolder
from .._helpers.func import get_func_kwargs
from .._helpers.asyncio import execute_coroutines
from ..session import BaseSession
from ..types import Scraper

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
        middleware_holder: MiddlewareHolder,
        pipeline_dispatcher: PipelineDispatcher,
        session: BaseSession,
    ) -> None:
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
            session=session,
            schedule_request=self._scheduler.spawn,
            queue=self._request_queue,
            delay=self._config.session.delay,
            shutdown_timeout=self._config.execution.shutdown_timeout,
            dependencies={"pipeline": self._pipeline_dispatcher.put_item, **self._dependencies},
            middleware_holder=middleware_holder,
        )

    async def run(self) -> None:
        "Start the scraping process."
        self._start_time = time.time()
        self._request_manager.listen_queue()

        try:
            await asyncio.gather(
                *[
                    scraper(
                        **get_func_kwargs(
                            scraper,
                            send_request=self._request_manager.sender,
                            pipeline=self._pipeline_dispatcher.put_item,
                            **self._dependencies,
                        )
                    )
                    for scraper in self._scrapers
                ]
            )
            await self._wait()
        finally:
            await self._wait()

    async def _wait(self) -> None:
        while len(self._scheduler) > 0 or self._request_queue.qsize() > 0:
            await asyncio.sleep(self._config.execution.shutdown_check_interval)

    async def close(self) -> None:
        "Close all resources and cleanup."
        await execute_coroutines(
            self._request_manager.close(),
            self._scheduler.close(),
            self._pipeline_dispatcher.close(),
        )
