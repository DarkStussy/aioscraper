from typing import Any, Callable, Type

from ..exceptions import AIOScraperException
from ..types.pipeline import (
    PipelineItemType,
    PipelineType,
    BasePipeline,
    PipelineMiddleware,
    PipelineContainer,
    PipelineMiddlewareStage,
)


class PipelineHolder:
    "Keeps pipeline containers and exposes decorator helpers."

    def __init__(self) -> None:
        self.pipelines: dict[Any, PipelineContainer] = {}

    def __call__(
        self,
        item_type: Type[PipelineItemType],
        *args,
        **kwargs,
    ) -> Callable[[Type[PipelineType]], Type[PipelineType]]:
        "Return a decorator that instantiates and registers a pipeline class."

        def decorator(pipeline_class: Type[PipelineType]) -> Type[PipelineType]:
            try:
                pipeline = pipeline_class(*args, **kwargs)
            except Exception as e:
                raise AIOScraperException(
                    f"Failed to instantiate pipeline {pipeline_class.__name__} with provided arguments"
                ) from e

            self.add(item_type, pipeline)
            return pipeline_class

        return decorator

    def add(self, item_type: Type[PipelineItemType], *pipelines: BasePipeline[PipelineItemType]) -> None:
        "Add pipelines to process scraped data."
        for pipeline in pipelines:
            # runtime protocol check to ensure BasePipeline interface compliance
            try:
                ok = isinstance(pipeline, BasePipeline)
            except TypeError as exc:
                raise AIOScraperException(
                    f"Invalid pipeline type {type(pipeline)!r}; expected an instance implementing BasePipeline protocol"
                ) from exc

            if not ok:
                raise AIOScraperException(
                    f"Pipeline {pipeline.__class__.__name__} does not implement required BasePipeline methods"
                )

        if item_type not in self.pipelines:
            self.pipelines[item_type] = PipelineContainer(pipelines=[*pipelines])
        else:
            self.pipelines[item_type].pipelines.extend(pipelines)

    def middleware(
        self,
        middleware_type: PipelineMiddlewareStage,
        item_type: Type[PipelineItemType],
    ) -> Callable[[PipelineMiddleware[PipelineItemType]], PipelineMiddleware[PipelineItemType]]:
        "Return a decorator that registers a pipeline middleware."

        def decorator(middleware: PipelineMiddleware[PipelineItemType]) -> PipelineMiddleware[PipelineItemType]:
            self.add_middlewares(middleware_type, item_type, middleware)
            return middleware

        return decorator

    def add_middlewares(
        self,
        middleware_type: PipelineMiddlewareStage,
        item_type: Type[PipelineItemType],
        *middlewares: PipelineMiddleware[PipelineItemType],
    ) -> None:
        "Add pipeline processing middlewares."

        for middleware in middlewares:
            # runtime protocol check to ensure PipelineMiddleware interface compliance
            try:
                ok = isinstance(middleware, PipelineMiddleware)
            except TypeError as exc:
                raise AIOScraperException(
                    f"Invalid middleware type {type(middleware)!r}; expected callable implementing PipelineMiddleware protocol"
                ) from exc

            if not ok:
                raise AIOScraperException(
                    f"Middleware {type(middleware).__name__} does not implement required PipelineMiddleware interface"
                )

        if item_type not in self.pipelines:
            container = self.pipelines[item_type] = PipelineContainer()
        else:
            container = self.pipelines[item_type]

        match middleware_type:
            case "pre":
                container.pre_middlewares.extend(middlewares)
            case "post":
                container.post_middlewares.extend(middlewares)
            case _:
                raise ValueError(f"Unsupported pipeline middleware type: {middleware_type}")
