Lifespan
========

A lifespan is an async context manager ``lifespan(scraper)`` that wraps the same :class:`AIOScraper <aioscraper.scraper.core.AIOScraper>` instance before CLI startup. Use it to create and tear down resources in one place.

What it does
------------
- Runs once before the scraper starts; you can register scrapers, pipelines, and middlewares here.
- Injects dependencies via :meth:`register_dependencies <aioscraper.scraper.core.AIOScraper.register_dependencies>` so callbacks receive them.
- Ensures teardown (closing clients, flushing buffers) happens even on errors.


.. code-block:: python

    from contextlib import asynccontextmanager
    from typing import Any, Self
    from aioscraper import AIOScraper
    from aioscraper.types import Request, SendRequest, Response

    class DbClient:
        @classmethod
        async def create(cls) -> Self:
            return cls()

        async def save(self, data: Any):
            print("saved:", data)

        async def close(self):
            print("db client closed")

    async def scrape(send_request: SendRequest):
        await send_request(Request(url="https://httpbin.org/get", callback=handle_response))

    async def handle_response(response: Response, db_client: DbClient):
        await db_client.save(response.json())

    @asynccontextmanager
    async def lifespan(scraper: AIOScraper):
        scraper.register(scrape)

        db_client = await DbClient.create()
        scraper.register_dependencies(db_client=db_client)

        try:
            yield
        finally:
            await db_client.close()

Notes
-----
- If a module exposes both ``scraper`` and ``lifespan``, the CLI applies ``lifespan(scraper)`` automatically.
- When you target ``lifespan`` explicitly via ``module:lifespan``, the CLI will create a new scraper for you.
