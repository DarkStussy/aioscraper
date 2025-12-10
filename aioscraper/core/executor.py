import asyncio
from logging import getLogger
from typing import Any

from aioscraper._helpers.asyncio import execute_coroutines
from aioscraper._helpers.func import get_func_kwargs
from aioscraper.config import Config
from aioscraper.holders import MiddlewareHolder
from aioscraper.types import Scraper

from .pipeline import PipelineDispatcher
from .request_manager import RequestManager
from .session import SessionMaker

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
        self._request_manager = RequestManager(
            scheduler_config=self._config.scheduler,
            rate_limit_config=self._config.session.rate_limit,
            retry_config=self._config.session.retry,
            shutdown_check_interval=self._config.execution.shutdown_check_interval,
            sessionmaker=sessionmaker,
            dependencies=self._dependencies,
            middleware_holder=middleware_holder,
        )

    async def run(self):
        "Start the scraping process."
        self._request_manager.start_listening()
        try:
            logger.debug("Running %d scraper(s) concurrently", len(self._scrapers))
            await asyncio.gather(
                *[
                    scraper(
                        **get_func_kwargs(
                            scraper,
                            send_request=self._request_manager.sender,
                            **self._dependencies,
                        ),
                    )
                    for scraper in self._scrapers
                ],
            )
            logger.debug("Waiting for pending requests")
            await self._request_manager.wait()
            logger.info("Executor finished: all scrapers and requests completed")
        finally:
            await self._request_manager.shutdown()

    async def close(self):
        "Close all resources and cleanup."
        await execute_coroutines(self._request_manager.close(), self._pipeline_dispatcher.close())
        logger.debug("Executor closed successfully")
