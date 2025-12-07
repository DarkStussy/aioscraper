import asyncio
from logging import getLogger
from typing import Any

from aiojobs import Scheduler


from .request_manager import RequestManager
from .pipeline import PipelineDispatcher
from .session import SessionMaker
from ..config import Config
from ..holders import MiddlewareHolder
from .._helpers.func import get_func_kwargs
from .._helpers.asyncio import execute_coroutines
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
        sessionmaker: SessionMaker,
    ):
        self._config = config
        self._scrapers = scrapers
        self._dependencies = {"config": config, "pipeline": pipeline_dispatcher.put_item, **dependencies}
        self._pipeline_dispatcher = pipeline_dispatcher
        self._scheduler = Scheduler(
            limit=self._config.scheduler.concurrent_requests,
            pending_limit=self._config.scheduler.pending_requests,
            close_timeout=self._config.scheduler.close_timeout,
        )
        self._request_manager = RequestManager(
            rate_limit_config=self._config.session.rate_limit,
            sessionmaker=sessionmaker,
            schedule=self._scheduler.spawn,
            dependencies=self._dependencies,
            middleware_holder=middleware_holder,
        )

    async def run(self):
        "Start the scraping process."
        self._request_manager.start_listening()

        try:
            await asyncio.gather(
                *[
                    scraper(**get_func_kwargs(scraper, send_request=self._request_manager.sender, **self._dependencies))
                    for scraper in self._scrapers
                ]
            )
            await self._wait()
        finally:
            await self._wait()

    async def _wait(self):
        while len(self._scheduler) > 0 or self._request_manager.active:
            await asyncio.sleep(self._config.execution.shutdown_check_interval)

    async def close(self):
        "Close all resources and cleanup."
        await execute_coroutines(
            self._request_manager.close(),
            self._scheduler.close(),
            self._pipeline_dispatcher.close(),
        )
