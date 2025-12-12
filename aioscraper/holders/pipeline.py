import logging
from typing import Any, Callable

from aioscraper._helpers.log import get_log_name
from aioscraper.exceptions import AIOScraperException
from aioscraper.types.pipeline import (
    BasePipeline,
    GlobalPipelineMiddleware,
    PipelineContainer,
    PipelineItemType,
    PipelineMiddleware,
    PipelineMiddlewareStage,
)

logger = logging.getLogger(__name__)


class PipelineHolder:
    "Keeps pipeline containers and exposes decorator helpers."

    def __init__(self):
        self.pipelines: dict[Any, PipelineContainer] = {}
        self.global_middlewares: list[Callable[..., GlobalPipelineMiddleware[Any]]] = []

    def __call__(
        self,
        item_type: type[PipelineItemType],
        *args,
        **kwargs,
    ) -> Callable[[type[BasePipeline[PipelineItemType]]], type[BasePipeline[PipelineItemType]]]:
        "Return a decorator that instantiates and registers a pipeline class for the given item type."

        def decorator(pipeline_class: type[BasePipeline[PipelineItemType]]) -> type[BasePipeline[PipelineItemType]]:
            try:
                pipeline = pipeline_class(*args, **kwargs)
            except Exception as e:
                raise AIOScraperException(
                    f"Failed to instantiate pipeline {pipeline_class.__name__} with provided arguments",
                ) from e

            self.add(item_type, pipeline)
            return pipeline_class

        return decorator

    def add(self, item_type: type[PipelineItemType], *pipelines: BasePipeline[PipelineItemType]):
        "Add pipelines to process scraped data."
        for pipeline in pipelines:
            # runtime protocol check to ensure BasePipeline interface compliance
            try:
                ok = isinstance(pipeline, BasePipeline)
            except TypeError as exc:
                raise AIOScraperException(
                    f"Invalid pipeline type {type(pipeline)!r}; "
                    "expected an instance implementing BasePipeline protocol",
                ) from exc

            pipeline_type = type(pipeline).__name__
            if not ok:
                raise AIOScraperException(f"Pipeline {pipeline_type} does not implement required BasePipeline methods")

            logger.debug("Installing pipeline %s: type=%s", pipeline_type, item_type.__name__)

        if item_type not in self.pipelines:
            self.pipelines[item_type] = PipelineContainer(pipelines=[*pipelines])
        else:
            self.pipelines[item_type].pipelines.extend(pipelines)

    def middleware(
        self,
        middleware_type: PipelineMiddlewareStage,
        item_type: type[PipelineItemType],
    ) -> Callable[[PipelineMiddleware[PipelineItemType]], PipelineMiddleware[PipelineItemType]]:
        "Return a decorator that registers a pipeline middleware for the given stage."

        def decorator(middleware: PipelineMiddleware[PipelineItemType]) -> PipelineMiddleware[PipelineItemType]:
            self.add_middlewares(middleware_type, item_type, middleware)
            return middleware

        return decorator

    def add_middlewares(
        self,
        middleware_type: PipelineMiddlewareStage,
        item_type: type[PipelineItemType],
        *middlewares: PipelineMiddleware[PipelineItemType],
    ):
        "Add pipeline processing middlewares."
        if item_type not in self.pipelines:
            container = self.pipelines[item_type] = PipelineContainer()
        else:
            container = self.pipelines[item_type]

        for middleware in middlewares:
            logger.debug("Installing pipeline middleware %s: type=%s", get_log_name(middleware), middleware_type)

        match middleware_type:
            case "pre":
                container.pre_middlewares.extend(middlewares)
            case "post":
                container.post_middlewares.extend(middlewares)
            case _:
                raise ValueError(f"Unsupported pipeline middleware type: {middleware_type}")

    def global_middleware(
        self,
        middleware: Callable[..., GlobalPipelineMiddleware[PipelineItemType]],
    ) -> Callable[..., GlobalPipelineMiddleware[PipelineItemType]]:
        """
        Add a global pipeline middleware factory.

        The callable can accept injected dependencies and must return a middleware with signature
        ``async def mw(handler, item): ...`` which wraps the entire pipeline chain for every item type.
        """
        self.add_global_middlewares(middleware)
        return middleware

    def add_global_middlewares(self, *middlewares: Callable[..., GlobalPipelineMiddleware[PipelineItemType]]):
        "Add global pipeline middlewares as factory."
        for middleware in middlewares:
            logger.debug("Installing global middleware %s", get_log_name(middleware))
            self.global_middlewares.append(middleware)
