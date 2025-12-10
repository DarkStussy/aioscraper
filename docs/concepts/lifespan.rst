Lifespan
========

Lifespan is an async context manager ``lifespan(scraper)`` that wraps the same :class:`AIOScraper <aioscraper.core.scraper.AIOScraper>` instance before startup. Use it to create and tear down resources in one place.

What it does
------------
- Runs once before the scraper starts; you can add scrapers, pipelines, and middlewares here.
- Injects dependencies via :meth:`add_dependencies <aioscraper.core.scraper.AIOScraper.add_dependencies>` so callbacks receive them.
- Ensures teardown (closing clients, flushing buffers) happens even on errors.


.. code-block:: python

    from typing import Iterable, Self
    from aioscraper import AIOScraper, Request, SendRequest, Response

    scraper = AIOScraper()


    class DbClient:
        @classmethod
        async def create(cls) -> Self:
            return cls()

        async def get(self) -> Iterable[int]:
            return list(range(3))

        async def close(self):
            print("db client closed")


    @scraper
    async def scrape(send_request: SendRequest, db_client: DbClient):
        for i in await db_client.get():
            await send_request(Request(url=f"https://example.com/?i={i}", callback=handle_response))


    async def handle_response(response: Response):
        print(f"{response.url}: {response.status}")


    @scraper.lifespan
    async def lifespan(scraper: AIOScraper):
        db_client = await DbClient.create()
        scraper.add_dependencies(db_client=db_client)

        try:
            yield
        finally:
            await db_client.close()
