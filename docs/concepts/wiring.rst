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

See :doc:`lifespan </concepts/lifespan>` for a complete setup/teardown example using these methods.
