import abc
from typing import Any


class BaseScraper(abc.ABC):
    """
    Abstract base class for implementing web scrapers.

    This class defines the interface that all scrapers must implement. It provides
    the basic structure for initializing, running, and cleaning up scrapers.
    """

    @abc.abstractmethod
    async def start(self, *args: Any, **kwargs: Any) -> None:
        """
        Starts the scraper.

        This method is called to start the scraper by sending the initial requests required for its operation.
        """
        ...

    async def close(self, *args: Any, **kwargs: Any) -> None:
        """
        Closes the scraper.

        This method is called to clean up any resources created by the scraper after it has finished running.
        """
        ...
