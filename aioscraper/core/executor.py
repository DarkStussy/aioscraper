import asyncio
from functools import partial
from logging import getLogger
from typing import Any

from aioscraper._helpers.asyncio import execute_coroutines
from aioscraper._helpers.deps import RESERVED_DEPENDENCIES, reject_reserved
from aioscraper._helpers.func import get_func_kwargs
from aioscraper.config import Config
from aioscraper.holders import MiddlewareHolder
from aioscraper.types import GroupBy, Scraper, ShouldRetry

from .errors import ErrorCollector
from .pipeline import PipelineDispatcher
from .request_manager import RequestManager
from .session import SessionMaker
from .stats import RunStats

logger = getLogger(__name__)


class ScraperExecutor:
    "Runs the scraper callables and owns the request manager they send through."

    def __init__(
        self,
        config: Config,
        scrapers: list[Scraper],
        dependencies: dict[str, Any],
        middleware_holder: MiddlewareHolder,
        pipeline_dispatcher: PipelineDispatcher,
        sessionmaker: SessionMaker,
        error_collector: ErrorCollector | None = None,
        stats: RunStats | None = None,
        group_by: GroupBy | None = None,
        should_retry: ShouldRetry | None = None,
    ):
        self._error_collector = ErrorCollector() if error_collector is None else error_collector
        self._config = config
        self._scrapers = scrapers
        # backstop for a direct build; AIOScraper checks before it wires anything
        reject_reserved(dependencies, RESERVED_DEPENDENCIES, "Dependency names")
        self._dependencies = {"config": config, "pipeline": pipeline_dispatcher.put_item, **dependencies}
        self._pipeline_dispatcher = pipeline_dispatcher
        self._request_manager = RequestManager(
            scheduler_config=self._config.scheduler,
            rate_limit_config=self._config.session.rate_limit,
            retry_config=self._config.session.retry,
            shutdown_check_interval=self._config.execution.shutdown_check_interval,
            max_error_body_size=self._config.session.max_error_body_size,
            buffer_body=self._config.session.buffer_body,
            group_by=group_by,
            should_retry=should_retry,
            sessionmaker=sessionmaker,
            dependencies=self._dependencies,
            middleware_holder=middleware_holder,
            error_collector=self._error_collector,
            stats=stats,
        )
        # the entrypoint sender waits for a free admission slot; the callbacks' does not
        self._scraper_dependencies = {
            "schedule_request": self._request_manager.sender,
            "send_request": self._request_manager.sender,
            **self._dependencies,
        }

    async def run(self):
        "Run every scraper at once, then wait for the requests they scheduled, retries included."
        self._request_manager.start_listening()
        try:
            logger.debug("Running %d scraper(s) concurrently", len(self._scrapers))
            await asyncio.gather(
                *[scraper(**get_func_kwargs(scraper, **self._scraper_dependencies)) for scraper in self._scrapers],
            )
            logger.debug("Waiting for pending requests")
            await self._request_manager.wait()
            logger.info("Executor finished: all scrapers and requests completed")
        finally:
            await self._request_manager.shutdown()

    async def close(self):
        "Close the request manager and the pipelines. A failure to close is recorded, not raised."
        await execute_coroutines(
            self._request_manager.close(),
            self._pipeline_dispatcher.close(),
            on_error=partial(self._error_collector.record, "close"),
        )
        logger.debug("Executor closed successfully")
