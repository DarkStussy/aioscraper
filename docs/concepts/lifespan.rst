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

Instance lifecycle
------------------

An :class:`AIOScraper <aioscraper.core.scraper.AIOScraper>` instance runs once. It goes from created to running on :meth:`start() <aioscraper.core.scraper.AIOScraper.start>` (or on entering ``async with``), and to closed on :meth:`close() <aioscraper.core.scraper.AIOScraper.close>` (or on leaving it). Starting a running or closed instance raises ``RuntimeError``: closing it closes the executor and its sessions, and neither is rebuilt, so scraping again takes a new instance:

.. code-block:: python

    from aioscraper import AIOScraper, run_scraper


    def build() -> AIOScraper:
        scraper = AIOScraper()
        ...
        return scraper


    async def main():
        for _ in range(3):
            await run_scraper(build())

A failed start is not a run: if the lifespan raises, it is unwound and the instance can still be started.

:meth:`wait() <aioscraper.core.scraper.AIOScraper.wait>` and :meth:`shutdown() <aioscraper.core.scraper.AIOScraper.shutdown>` stay usable once the run is over: they return the recorded :class:`RunResult <aioscraper.core.errors.RunResult>` when the scraper is closed, and raise ``RuntimeError`` when it was never started — closing an unstarted scraper does not make them report a clean run. The result describes the run rather than the call: ``timed_out`` stays set on every later result, and both wait for teardown before reporting, so the errors recorded while the executor closed are included. A ``close()`` landing while ``wait()`` is in flight is reported that way too, instead of canceling it.

:meth:`close() <aioscraper.core.scraper.AIOScraper.close>` can be called any number of times and from several tasks at once. The later calls wait for the teardown the first one started, and a call landing while the scraper is still starting waits for the startup to settle instead of closing an instance whose resources are half set up.
