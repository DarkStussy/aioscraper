import abc


class BaseScraper(abc.ABC):
    """
    Abstract base class for implementing web scrapers.

    This class defines the interface that all scrapers must implement. It provides
    the basic structure for initializing, running, and cleaning up scrapers.
    """

    @abc.abstractmethod
    async def start(self, *args, **kwargs) -> None:
        """
        Starts the scraper.

        This method is called to start the scraper by sending the initial requests required for its operation.
        """
        ...

    async def initialize(self, *args, **kwargs) -> None:
        """
        Initializes the scraper.

        This method is called before starting the scraper It should be used to initialize any
        necessary state or resources required by the scraper.
        """
        ...

    async def close(self, *args, **kwargs) -> None:
        """
        Closes the scraper.

        This method is called to clean up any resources created by the scraper after it has finished running.
        """
        ...
