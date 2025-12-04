from typing import Protocol, TypeVar


class BaseItem(Protocol):
    @property
    def pipeline_name(self) -> str: ...


ItemType = TypeVar("ItemType", bound=BaseItem)


class Pipeline(Protocol):
    "Processes an item by passing it through the appropriate pipelines"

    async def __call__(self, item: BaseItem) -> BaseItem: ...


class PipelineMiddleware(Protocol[ItemType]):
    async def __call__(self, item: ItemType) -> ItemType: ...
