from logging import getLogger
from typing import Any, Generator, Mapping, Sequence

from aioscraper.types.pipeline import PipelineMiddleware

from .base import BasePipeline, BaseItem
from ..exceptions import PipelineException

logger = getLogger(__name__)


class PipelineDispatcher:
    "A class for managing and dispatching items through processing pipelines"

    def __init__(self, pipelines: Mapping[str, Sequence[BasePipeline[Any]]]) -> None:
        self._pipelines = pipelines
        self._pre_processing_middlewares = []
        self._post_processing_middlewares = []

    def add_pre_processing_middlewares(self, *middlewares: PipelineMiddleware) -> None:
        self._pre_processing_middlewares.extend(middlewares)

    def add_post_processing_middlewares(self, *middlewares: PipelineMiddleware) -> None:
        self._post_processing_middlewares.extend(middlewares)

    async def put_item(self, item: BaseItem) -> BaseItem:
        "Processes an item by passing it through the appropriate pipelines"
        logger.debug(f"pipeline item received: {item}")

        for middleware in self._pre_processing_middlewares:
            await middleware(item)

        try:
            pipelines = self._pipelines[item.pipeline_name]
        except KeyError:
            raise PipelineException(f"Pipelines for item {item} not found")

        for pipeline in pipelines:
            await pipeline.put_item(item)

        for middleware in self._post_processing_middlewares:
            await middleware(item)

        return item

    def _get_pipelines(self) -> Generator[BasePipeline[Any], None, None]:
        for pipelines in self._pipelines.values():
            for pipeline in pipelines:
                yield pipeline

    async def close(self) -> None:
        """
        Closes all pipelines.

        Calls the close() method for each pipeline in the system.
        """
        for pipeline in self._get_pipelines():
            await pipeline.close()
