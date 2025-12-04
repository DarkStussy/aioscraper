import abc
from typing import Generic

from ..types import ItemType


class BasePipeline(abc.ABC, Generic[ItemType]):
    "Base abstract class for implementing data processing pipelines."

    @abc.abstractmethod
    async def put_item(self, item: ItemType) -> ItemType:
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
