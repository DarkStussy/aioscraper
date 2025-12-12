from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypeVar, runtime_checkable

PipelineItemType = TypeVar("PipelineItemType")

PipelineMiddlewareStage = Literal["pre", "post"]


@runtime_checkable
class BasePipeline(Protocol[PipelineItemType]):
    "Interface for classes that process scraped items of a specific type."

    async def put_item(self, item: PipelineItemType) -> PipelineItemType:
        """
        Process an item and return it (mutated or replaced).

        This method must be implemented by all concrete pipeline classes.
        """
        ...

    async def close(self):
        """
        Close the pipeline.

        This method is called when the pipeline is no longer needed.
        It can be overridden to perform any necessary cleanup operations.
        """
        ...


class PipelineMiddleware(Protocol[PipelineItemType]):
    "Async hook used before or after pipeline execution; must return the item."

    async def __call__(self, item: PipelineItemType) -> PipelineItemType: ...


class Pipeline(Protocol[PipelineItemType]):
    """Protocol for callables that accept an item and return the processed item."""

    async def __call__(self, item: PipelineItemType) -> PipelineItemType: ...


ItemHandler = Pipeline


class GlobalPipelineMiddleware(Protocol[PipelineItemType]):
    "Wrapper invoked around the entire pipeline chain for every item type."

    async def __call__(self, handler: ItemHandler, item: PipelineItemType) -> PipelineItemType: ...


@dataclass(slots=True, kw_only=True)
class PipelineContainer:
    pipelines: list[BasePipeline[Any]] = field(default_factory=list)
    pre_middlewares: list[PipelineMiddleware[Any]] = field(default_factory=list)
    post_middlewares: list[PipelineMiddleware[Any]] = field(default_factory=list)
