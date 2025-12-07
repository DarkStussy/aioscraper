Wiring scrapers and dependencies
================================

`AIOScraper` lets you compose scrapers and shared dependencies before starting execution.

Scrapers
--------
- :meth:`__call__ <aioscraper.core.scraper.AIOScraper.__call__>`: Add one or more async scraper callables; returns the first so you can use it as a decorator.

Dependencies
------------
- :meth:`add_dependencies <aioscraper.core.scraper.AIOScraper.add_dependencies>`: Attach arbitrary objects (clients, configs, services) that become injectable into callbacks via dependency resolution.


.. code-block:: python

    from aioscraper import AIOScraper, Request, SendRequest


    async def scrape_one(send_request: SendRequest):
        await send_request(Request(url="https://example.com"))


    async def scrape_two(send_request: SendRequest):
        await send_request(Request(url="https://example.com"))


    def create_scraper() -> AIOScraper:
        scraper = AIOScraper(scrape_one, scrape_two)
        scraper.add_dependencies(api_key="secret")
        return scraper
