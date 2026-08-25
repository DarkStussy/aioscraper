from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Protocol, TypeVar, runtime_checkable

PipelineItemType = TypeVar("PipelineItemType")

PipelineMiddlewareStage = Literal["pre", "post"]


@runtime_checkable
class BasePipeline(Protocol[PipelineItemType]):
    "Interface for classes that process scraped items of a specific type."

    async def put_item(self, item: PipelineItemType) -> PipelineItemType:
        "Handle one item and return it, mutated or replaced. The next pipeline receives what you return."
        ...

    async def close(self):
        "Called once when the run ends, for flushing buffers and closing what the pipeline opened."
        ...


class PipelineMiddleware(Protocol[PipelineItemType]):
    "Hook running before or after the pipelines of one item type; must return the item."

    async def __call__(self, item: PipelineItemType) -> PipelineItemType: ...


class Pipeline(Protocol[PipelineItemType]):
    "The ``pipeline`` dependency callbacks receive: hand it an item, get the processed one back."

    async def __call__(self, item: PipelineItemType) -> PipelineItemType: ...


ItemHandler = Pipeline


class GlobalPipelineMiddleware(Protocol[PipelineItemType]):
    "Wraps the whole chain, whatever the item type. Must ``await handler(item)`` to keep it moving."

    async def __call__(self, handler: ItemHandler, item: PipelineItemType) -> PipelineItemType: ...


GlobalPipelineMiddlewareFactory = Callable[..., GlobalPipelineMiddleware[PipelineItemType]]


@dataclass(slots=True, kw_only=True)
class PipelineContainer:
    pipelines: list[BasePipeline[Any]] = field(default_factory=list)
    pre_middlewares: list[PipelineMiddleware[Any]] = field(default_factory=list)
    post_middlewares: list[PipelineMiddleware[Any]] = field(default_factory=list)
