from typing import Callable, Literal, Type, TypeVar


from ..exceptions import AIOScraperException
from ..pipeline.base import BasePipeline
from ..pipeline.dispatcher import PipelineContainer
from ..types import ItemType, PipelineMiddleware

PipelineMiddlewareType = Literal["pre", "post"]
PipelineT = TypeVar("PipelineT", bound=BasePipeline)


class PipelineHolder:
    "Keeps pipeline containers and exposes decorator helpers."

    def __init__(self) -> None:
        self.pipelines: dict[str, PipelineContainer] = {}

    def __call__(
        self,
        name: str,
        *args,
        **kwargs,
    ) -> Callable[[Type[PipelineT]], Type[PipelineT]]:
        "Return a decorator that instantiates and registers a pipeline class."

        def decorator(pipeline_class: Type[PipelineT]) -> Type[PipelineT]:
            try:
                pipeline = pipeline_class(*args, **kwargs)
            except Exception as e:
                raise AIOScraperException(
                    f"Failed to instantiate pipeline {pipeline_class.__name__} with provided arguments"
                ) from e

            self.add(name, pipeline)
            return pipeline_class

        return decorator

    def add(self, name: str, *pipelines: BasePipeline[ItemType]) -> None:
        "Add pipelines to process scraped data."
        if name not in self.pipelines:
            self.pipelines[name] = PipelineContainer(pipelines=[*pipelines])
        else:
            self.pipelines[name].pipelines.extend(pipelines)

    def middleware(
        self,
        middleware_type: PipelineMiddlewareType,
        name: str,
    ) -> Callable[[PipelineMiddleware[ItemType]], PipelineMiddleware[ItemType]]:
        "Return a decorator that registers a pipeline middleware."

        def decorator(middleware: PipelineMiddleware[ItemType]) -> PipelineMiddleware[ItemType]:
            self.add_middlewares(middleware_type, name, middleware)
            return middleware

        return decorator

    def add_middlewares(
        self,
        middleware_type: PipelineMiddlewareType,
        name: str,
        *middlewares: PipelineMiddleware[ItemType],
    ) -> None:
        "Add pipeline processing middlewares."

        if name not in self.pipelines:
            container = self.pipelines[name] = PipelineContainer()
        else:
            container = self.pipelines[name]

        match middleware_type:
            case "pre":
                container.pre_middlewares.extend(middlewares)
            case "post":
                container.post_middlewares.extend(middlewares)
            case _:
                raise ValueError(f"Unsupported pipeline middleware type: {middleware_type}")
