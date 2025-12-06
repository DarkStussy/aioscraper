from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypeVar, runtime_checkable


PipelineType = TypeVar("PipelineType", bound="BasePipeline[Any]")
PipelineItemType = TypeVar("PipelineItemType")

PipelineMiddlewareStage = Literal["pre", "post"]


@runtime_checkable
class BasePipeline(Protocol[PipelineItemType]):
    "Base class for implementing data processing pipelines."

    async def put_item(self, item: PipelineItemType) -> PipelineItemType:
        """
        Process a item.

        This method must be implemented by all concrete pipeline classes.
        """
        ...

    async def close(self) -> None:
        """
        Close the pipeline.

        This method is called when the pipeline is no longer needed.
        It can be overridden to perform any necessary cleanup operations.
        """
        ...


@runtime_checkable
class PipelineMiddleware(Protocol[PipelineItemType]):
    async def __call__(self, item: PipelineItemType) -> PipelineItemType: ...


class Pipeline(Protocol):
    """
    Callable interface matching `PipelineDispatcher.put_item`,
    injected as the `pipeline` dependency to push items through registered pipelines.
    """

    async def __call__(self, item: PipelineItemType) -> PipelineItemType: ...


@dataclass(slots=True, kw_only=True)
class PipelineContainer:
    pipelines: list[BasePipeline[Any]] = field(default_factory=list)
    pre_middlewares: list[PipelineMiddleware[Any]] = field(default_factory=list)
    post_middlewares: list[PipelineMiddleware[Any]] = field(default_factory=list)
