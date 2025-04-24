from typing import Protocol


class BaseItem(Protocol):
    @property
    def pipeline_name(self) -> str: ...


class Pipeline(Protocol):
    "Processes an item by passing it through the appropriate pipelines"

    async def __call__(self, item: BaseItem) -> BaseItem: ...
