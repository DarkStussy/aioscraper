from logging import getLogger
from typing import Any, Callable, Mapping

from aioscraper._helpers.func import get_func_kwargs
from aioscraper._helpers.log import get_log_name
from aioscraper.config import PipelineConfig
from aioscraper.exceptions import PipelineException, StopItemProcessing, StopMiddlewareProcessing
from aioscraper.types.pipeline import GlobalPipelineMiddleware, Pipeline, PipelineContainer, PipelineItemType

logger = getLogger(__name__)


class PipelineDispatcher:
    "Routes items through the registered pipeline chain."

    def __init__(
        self,
        config: PipelineConfig,
        pipelines: Mapping[Any, PipelineContainer],
        global_middlewares: list[Callable[..., GlobalPipelineMiddleware[Any]]] | None = None,
        dependencies: Mapping[str, Any] | None = None,
    ):
        self._config = config
        self._pipelines = pipelines
        self._global_middlewares = global_middlewares or []
        self._dependencies: Mapping[str, Any] = dependencies or {}
        logger.info(
            "Pipeline dispatcher created: pipelines=%d, global_middlewares=%d, strict=%s",
            len(pipelines),
            len(self._global_middlewares),
            config.strict,
        )
        self._handler = self._build_handler()

    async def _put_item(self, item: PipelineItemType) -> PipelineItemType:
        "Processes an item through pre-middleware, pipelines, and post-middleware for its type."
        item_type = type(item).__name__
        logger.debug("Pipeline item received: %s", item)

        try:
            pipe_container = self._pipelines[type(item)]
        except KeyError:
            if self._config.strict:
                logger.exception("Pipeline not found for item type %s (strict mode)", item_type)
                raise PipelineException(f"Pipelines for item {item_type} not found") from None

            logger.warning("Pipeline not found for item type %s, skipping", item_type)
            return item

        for middleware in pipe_container.pre_middlewares:
            try:
                item = await middleware(item)
            except StopMiddlewareProcessing:
                logger.debug("StopMiddlewareProcessing in pre middleware for %s: stopping pre chain", item_type)
                break
            except StopItemProcessing:
                logger.debug("StopItemProcessing in pre middleware for %s: aborting", item_type)
                return item

        for pipeline in pipe_container.pipelines:
            item = await pipeline.put_item(item)

        for middleware in pipe_container.post_middlewares:
            try:
                item = await middleware(item)
            except StopMiddlewareProcessing:
                logger.debug("StopMiddlewareProcessing in post middleware for %s: stopping post chain", item_type)
                break
            except StopItemProcessing:
                logger.debug("StopItemProcessing in post middleware for %s: aborting", item_type)
                return item

        return item

    def _build_handler(self) -> Pipeline[Any]:
        async def handler(item: PipelineItemType) -> PipelineItemType:
            return await self._put_item(item)

        for mv_factory in self._global_middlewares:
            try:
                logger.debug("Instantiating global middleware: %s", get_log_name(mv_factory))
                mw = mv_factory(**get_func_kwargs(mv_factory, **self._dependencies))
            except Exception as e:
                raise PipelineException(f"Failed to instantiate global middleware {get_log_name(mv_factory)}") from e

            next_handler = handler

            async def wrapped(
                item: PipelineItemType,
                _mw: GlobalPipelineMiddleware[PipelineItemType] = mw,
                _next: Pipeline[PipelineItemType] = next_handler,
            ):
                return await _mw(_next, item)

            handler = wrapped

        return handler

    async def put_item(self, item: PipelineItemType) -> PipelineItemType:
        "Dispatches an item through the pipeline."
        try:
            return await self._handler(item)
        except StopItemProcessing:
            logger.debug("StopItemProcessing in pipeline handler: aborting item processing")
            return item

    async def close(self):
        """
        Closes all pipelines.

        Calls the close() method for each pipeline in the system.
        """
        total_pipelines = sum(len(pc.pipelines) for pc in self._pipelines.values())
        logger.debug("Closing pipeline dispatcher: %d pipeline(s) to close", total_pipelines)

        for item_type, pipe_container in self._pipelines.items():
            for pipeline in pipe_container.pipelines:
                try:
                    await pipeline.close()
                except Exception:
                    logger.exception("Error closing pipeline for type %s", get_log_name(item_type))
