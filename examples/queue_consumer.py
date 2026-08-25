"""
AIOScraper as a queue consumer: Redis Pub/Sub -> aioscraper -> fetched pages.

The entrypoint runs for the life of the process, taking URLs off a channel. Requests are
acknowledged in the callback, and SCHEDULER_READY_QUEUE_MAX_SIZE keeps the consumer from
reading faster than the scraper drains.

Requires faststream and a Redis:

    $ pip install "aioscraper[aiohttp]" "faststream[redis]"
    $ docker run -d -p 6379:6379 --name redis redis:latest

Run it:

    $ export SCHEDULER_READY_QUEUE_MAX_SIZE=100
    $ aioscraper queue_consumer

Send it work from anywhere:

    $ docker exec -it redis redis-cli
    redis> PUBLISH test-channel "https://example.com"
    redis> PUBLISH test-channel "https://www.python.org"
"""

from dataclasses import dataclass
from typing import Self

from faststream.redis import RedisBroker, RedisChannelMessage
from faststream.redis.subscriber.usecases import ChannelSubscriber

from aioscraper import AIOScraper, Request, Response, ScheduleRequest, compiled

scraper = AIOScraper()


@dataclass(slots=True)
class Task:
    "A URL to fetch, with the message it came from so the callback can acknowledge it."

    id: str
    url: str
    message: RedisChannelMessage

    @classmethod
    def from_msg(cls, message: RedisChannelMessage) -> Self:
        return cls(id=message.message_id, url=message.body.decode(), message=message)


@scraper
async def scrape(schedule_request: ScheduleRequest, subscriber: ChannelSubscriber):
    "Runs until shutdown: every message becomes a request, and the loop blocks when the queue is full."
    async for msg in subscriber:
        task = Task.from_msg(msg)
        await schedule_request(
            Request(
                task.url,
                callback=callback,
                errback=errback,
                cb_kwargs={"task": task},
            ),
        )


@compiled
async def callback(response: Response, task: Task):
    print(f"[page] {task.id}: {response.url} - {response.status}")
    await task.message.ack()


@compiled
async def errback(exc: Exception, task: Task):
    print(f"[error] {task.id}: {task.url} - {exc}")


@scraper.lifespan
async def lifespan(scraper: AIOScraper):
    "The subscriber outlives the run and is injected by name, so the entrypoint can ask for it."
    async with RedisBroker("redis://localhost:6379") as broker:
        subscriber = broker.subscriber("test-channel", persistent=False)
        scraper.add_dependencies(subscriber=subscriber)
        await subscriber.start()

        yield

        await subscriber.stop()
