from logging import getLogger
from typing import Any, Mapping

from dataclasses import dataclass, field

from .base import BasePipeline
from ..config import PipelineConfig
from ..exceptions import PipelineException
from ..types.pipeline import PipelineMiddleware, BaseItem

logger = getLogger(__name__)


@dataclass(slots=True, kw_only=True)
class PipelineContainer:
    pipelines: list[BasePipeline[Any]] = field(default_factory=list)
    pre_middlewares: list[PipelineMiddleware[Any]] = field(default_factory=list)
    post_middlewares: list[PipelineMiddleware[Any]] = field(default_factory=list)


class PipelineDispatcher:
    "A class for managing and dispatching items through processing pipelines."

    def __init__(self, config: PipelineConfig, pipelines: Mapping[str, PipelineContainer]) -> None:
        self._config = config
        self._pipelines = pipelines

    async def put_item(self, item: BaseItem) -> BaseItem:
        "Processes an item by passing it through the appropriate pipelines."
        logger.debug(f"pipeline item received: {item}")

        try:
            pipe_container = self._pipelines[item.pipeline_name]
        except KeyError:
            if self._config.strict:
                raise PipelineException(f"Pipelines for item {item} not found")

            logger.warning(f"pipelines for item {item} not found")
            return item

        for middleware in pipe_container.pre_middlewares:
            item = await middleware(item)

        for pipeline in pipe_container.pipelines:
            item = await pipeline.put_item(item)

        for middleware in pipe_container.post_middlewares:
            item = await middleware(item)

        return item

    async def close(self) -> None:
        """
        Closes all pipelines.

        Calls the close() method for each pipeline in the system.
        """
        for pipe_container in self._pipelines.values():
            for pipeline in pipe_container.pipelines:
                await pipeline.close()
