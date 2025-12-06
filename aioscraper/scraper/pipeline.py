from logging import getLogger
from typing import Any, Callable, Mapping

from ..config import PipelineConfig
from ..exceptions import PipelineException, StopMiddlewareProcessing, StopItemProcessing
from .._helpers.func import get_func_kwargs
from ..types.pipeline import GlobalPipelineMiddleware, Pipeline, PipelineContainer, PipelineItemType

logger = getLogger(__name__)


class PipelineDispatcher:
    "A class for managing and dispatching items through processing pipelines."

    def __init__(
        self,
        config: PipelineConfig,
        pipelines: Mapping[Any, PipelineContainer],
        global_middlewares: list[Callable[..., GlobalPipelineMiddleware[Any]]] | None = None,
        dependencies: Mapping[str, Any] | None = None,
    ) -> None:
        self._config = config
        self._pipelines = pipelines
        self._global_middlewares = global_middlewares or []
        self._dependencies: Mapping[str, Any] = dependencies or {}
        self._handler = self._build_handler()

    async def _put_item(self, item: PipelineItemType) -> PipelineItemType:
        "Processes an item by passing it through the appropriate pipelines."
        logger.debug(f"pipeline item received: {item}")

        try:
            pipe_container = self._pipelines[type(item)]
        except KeyError:
            if self._config.strict:
                raise PipelineException(f"Pipelines for item {type(item)} not found")

            logger.warning(f"pipelines for item {type(item)} not found")
            return item

        for middleware in pipe_container.pre_middlewares:
            try:
                item = await middleware(item)
            except StopMiddlewareProcessing:
                logger.debug("StopMiddlewareProcessing in pipeline pre middleware: stopping pre chain")
                break
            except StopItemProcessing:
                logger.debug("StopItemProcessing in pipeline pre middleware: aborting item processing")
                return item

        for pipeline in pipe_container.pipelines:
            item = await pipeline.put_item(item)

        for middleware in pipe_container.post_middlewares:
            try:
                item = await middleware(item)
            except StopMiddlewareProcessing:
                logger.debug("StopMiddlewareProcessing in pipeline post middleware: stopping post chain")
                break
            except StopItemProcessing:
                logger.debug("StopItemProcessing in pipeline post middleware: aborting item processing")
                return item

        return item

    def _build_handler(self) -> Pipeline[Any]:
        async def handler(item: PipelineItemType) -> PipelineItemType:
            return await self._put_item(item)

        for mv_func in self._global_middlewares:
            try:
                mw = mv_func(**get_func_kwargs(mv_func, **self._dependencies))
            except Exception as e:
                raise PipelineException(f"Failed to instantiate global middleware {mv_func.__name__}") from e

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
        return await self._handler(item)

    async def close(self) -> None:
        """
        Closes all pipelines.

        Calls the close() method for each pipeline in the system.
        """
        for pipe_container in self._pipelines.values():
            for pipeline in pipe_container.pipelines:
                await pipeline.close()
