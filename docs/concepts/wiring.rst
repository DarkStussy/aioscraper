Wiring scrapers and dependencies
================================

`AIOScraper` lets you compose scrapers and shared dependencies before starting execution.

Scrapers
--------
- :meth:`register <aioscraper.scraper.core.AIOScraper.register>`: Add a single async callable scraper; returns the scraper so you can use it as a decorator.
- :meth:`register_all <aioscraper.scraper.core.AIOScraper.register_all>`: Add multiple scraper callables at once.

Dependencies
------------
- :meth:`register_dependencies <aioscraper.scraper.core.AIOScraper.register_dependencies>`: Attach arbitrary objects (clients, configs, services) that become injectable into callbacks via dependency resolution.


.. code-block:: python

    from aioscraper import AIOScraper
    from aioscraper.types import Request, SendRequest


    async def scrape_one(send_request: SendRequest):
        await send_request(Request(url="https://example.com"))


    async def scrape_two(send_request: SendRequest):
        await send_request(Request(url="https://example.com"))


    def create_scraper() -> AIOScraper:
        scraper = AIOScraper()
        scraper.register_all(scrape_one, scrape_two)
        scraper.register_dependencies(api_key="secret")
        return scraper
