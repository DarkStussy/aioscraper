"""
Cryptocurrency price scraper module using CoinMarketCap API.

This scraper integrates with AIOScraper and processes tasks from a queue,
fetching current cryptocurrency prices and updating them in the database.
"""

import asyncio
import logging
from json import JSONDecodeError

from database import CryptoCurrencyDatabase
from models import Task, TaskStatus

from aioscraper import Request, Response, SendRequest

logger = logging.getLogger(__name__)

# Currency to convert quotes to
CONVERT_CURRENCY = "USD"


class CryptocurrencyPriceScraper:
    """
    Scraper for fetching cryptocurrency prices via CoinMarketCap API.

    This class integrates with AIOScraper and processes tasks from a queue,
    sending requests to CoinMarketCap API to fetch current price quotes.

    Args:
        cmc_api_key (str): API key for accessing CoinMarketCap Pro API
    """

    def __init__(self, cmc_api_key: str):
        self._cmc_api_key = cmc_api_key

    async def __call__(self, send_request: SendRequest, queue: asyncio.Queue[Task]):
        """
        Main task processing loop.

        Continuously reads tasks from the queue and sends HTTP requests
        to CoinMarketCap API to fetch cryptocurrency quotes.

        Args:
            send_request (SendRequest): Function for sending HTTP requests (provided by AIOScraper)
            queue (asyncio.Queue[Task]): Task queue to process
        """
        while True:
            task = await queue.get()

            # Build and send request to CoinMarketCap API
            await send_request(
                Request(
                    url="https://pro-api.coinmarketcap.com/v1/cryptocurrency/quotes/latest",
                    params={"symbol": task.cryptocurrency.name, "convert": CONVERT_CURRENCY},
                    headers={
                        "X-CMC_PRO_API_KEY": self._cmc_api_key,
                        "Accept": "application/json",
                    },
                    callback=self._callback,
                    errback=self._errback,
                    cb_kwargs={"task": task},
                ),
            )

    async def _callback(self, response: Response, task: Task, database: CryptoCurrencyDatabase):
        """
        Handler for successful HTTP response from CoinMarketCap API.

        Extracts the cryptocurrency price from JSON response, updates it in the database
        and marks the task as successfully completed.

        Args:
            response (Response): HTTP response from API
            task (Task): Task being processed
            database (CryptoCurrencyDatabase): Database instance to save results
        """
        try:
            data = await response.json()
            price = data["data"][task.cryptocurrency.name]["quote"][CONVERT_CURRENCY]["price"]
        except (JSONDecodeError, KeyError, ValueError):
            logger.exception("%s: invalid response: %s", task.cryptocurrency.name, await response.text())
            return

        logger.info("%s: updated price: %s", task.cryptocurrency.name, price)

        # Update price and task status in database
        await database.update_price(task.cryptocurrency.id, price)
        await database.update_task_status(task.id, TaskStatus.SUCCESS)
        await database.commit()

    async def _errback(self, exc: Exception, task: Task):
        """
        Error handler for HTTP request failures.

        Logs error information with full stack trace.

        Args:
            exc: Exception that occurred
            task: Task being processed when error occurred
        """
        logger.error("%s: %s", task, exc, exc_info=exc)
