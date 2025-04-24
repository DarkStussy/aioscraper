from logging import Logger
from typing import Generator

from .base import BasePipeline, BaseItem
from ..exceptions import PipelineException


class PipelineDispatcher:
    "A class for managing and dispatching items through processing pipelines"

    def __init__(self, logger: Logger, pipelines: dict[str, list[BasePipeline]]) -> None:
        self._logger = logger
        self._pipelines = pipelines

    async def put_item(self, item: BaseItem) -> BaseItem:
        "Processes an item by passing it through the appropriate pipelines"
        self._logger.debug(f"pipeline item received: {item}")
        try:
            pipelines = self._pipelines[item.pipeline_name]
        except KeyError:
            raise PipelineException(f"Pipelines for item {item} not found")

        for pipeline in pipelines:
            await pipeline.put_item(item)

        return item

    def _get_pipelines(self) -> Generator[BasePipeline, None, None]:
        for pipelines in self._pipelines.values():
            for pipeline in pipelines:
                yield pipeline

    async def initialize(self) -> None:
        """
        Initializes all pipelines.

        Calls the initialize() method for each pipeline in the system.
        """
        for pipeline in self._get_pipelines():
            await pipeline.initialize()

    async def close(self) -> None:
        """
        Closes all pipelines.

        Calls the close() method for each pipeline in the system.
        """
        for pipeline in self._get_pipelines():
            await pipeline.close()
