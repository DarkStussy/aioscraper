import abc
from typing import TypeVar, Generic

from ..types import BaseItem

ItemType = TypeVar("ItemType", bound=BaseItem)


class BasePipeline(abc.ABC, Generic[ItemType]):
    "Base abstract class for implementing data processing pipelines"

    @abc.abstractmethod
    async def put_item(self, item: ItemType) -> None:
        """
        Process a item.

        This method must be implemented by all concrete pipeline classes.
        """
        ...

    async def initialize(self) -> None:
        """
        Initialize the pipeline.

        This method is called before the pipeline starts processing items.
        It can be overridden to perform any necessary setup operations.
        """
        ...

    async def close(self) -> None:
        """
        Close the pipeline.

        This method is called when the pipeline is no longer needed.
        It can be overridden to perform any necessary cleanup operations.
        """
        ...
