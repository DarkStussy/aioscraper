"""
AIOScraper as a queue consumer with FastStream and Redis.

This example demonstrates how aioscraper can act as a message queue consumer,
receiving scraping requests from Redis Pub/Sub and processing them asynchronously.

Architecture:
    Producer (any service) -> Redis Channel -> aioscraper (consumer) -> Process URLs

Prerequisites:
    $ pip install aioscraper[aiohttp] faststream[redis]

    # Start Redis (using Docker):
    $ docker run -d -p 6379:6379 --name redis redis:latest

Run the example:
    $ export SCHEDULER_READY_QUEUE_MAX_SIZE=100
    $ aioscraper queue_consumer

Send tasks from another service (example using redis-cli):
    $ docker exec -it redis redis-cli
    redis> SELECT 1
    redis> PUBLISH test-channel "https://example.com"
    redis> PUBLISH test-channel "https://httpbin.org/html"
    redis> PUBLISH test-channel "https://www.python.org"
"""

from dataclasses import dataclass
from typing import Self

from faststream.redis import RedisBroker, RedisChannelMessage
from faststream.redis.subscriber.usecases import ChannelSubscriber

from aioscraper import AIOScraper, Request, Response, SendRequest

scraper = AIOScraper()


@dataclass(slots=True)
class Task:
    """
    Scraping task received from the message queue.

    Attributes:
        id: Unique task identifier from Redis message
        url: URL to scrape
        message: Original Redis message for acknowledgment
    """

    id: str
    url: str
    message: RedisChannelMessage

    @classmethod
    def from_msg(cls, message: RedisChannelMessage) -> Self:
        """Create a Task from a Redis channel message."""
        return cls(id=message.message_id, url=message.body.decode(), message=message)


@scraper
async def scrape(send_request: SendRequest, subscriber: ChannelSubscriber):
    """
    Main consumer loop that listens to the Redis channel.

    This function continuously receives messages from the Redis channel,
    parses them into scraping tasks, and sends HTTP requests via aioscraper.
    """
    async for msg in subscriber:
        task = Task.from_msg(msg)
        await send_request(
            Request(
                url=task.url,
                callback=callback,
                errback=errback,
                cb_kwargs={"task": task},
            ),
        )


async def callback(response: Response, task: Task):
    """
    Success callback for processing scraped pages.

    Extracts the page title and acknowledges the message in Redis.
    """
    print(f"[page] {task.id}: {response.url} - {response.status}")
    await task.message.ack()


async def errback(exc: Exception, task: Task):
    """Error callback for handling scraping failures."""
    print(f"[error] {task.id}: {task.url} - {exc}")


@scraper.lifespan
async def lifespan(scraper: AIOScraper):
    """
    Lifespan manager for setting up and tearing down resources.

    This function:
    1. Connects to Redis broker
    2. Creates a channel subscriber
    3. Injects subscriber as dependency into scraper callbacks
    4. Cleans up resources on shutdown
    """
    async with RedisBroker("redis://localhost:6379") as broker:
        subscriber = broker.subscriber("test-channel", persistent=False)
        scraper.add_dependencies(subscriber=subscriber)
        await subscriber.start()

        yield

        await subscriber.stop()
