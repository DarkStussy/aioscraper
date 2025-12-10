Wiring scrapers and dependencies
================================

``AIOScraper`` uses dependency injection to provide shared resources (database clients, API clients, configs, services) to your callbacks, errbacks, pipelines, and middlewares. Dependencies are resolved automatically by parameter name and type hints.

How it works
------------

1. **Register dependencies** via ``add_dependencies(**kwargs)`` - typically in a lifespan context manager
2. **Request dependencies** in your callbacks/pipelines via parameter names
3. **aioscraper injects them automatically** when calling your functions based on parameter name or type

This makes testing easy (mock dependencies) and keeps your code decoupled from resource management.

Scrapers
--------
:meth:`__call__ <aioscraper.core.scraper.AIOScraper.__call__>`: Add one or more async scraper callables (entry points). Returns the first callable so you can use it as a decorator.

Dependencies
------------
:meth:`add_dependencies <aioscraper.core.scraper.AIOScraper.add_dependencies>`: Register objects (clients, configs, services) that become injectable into callbacks, errbacks, pipelines, and middlewares via type hints.

Example
-------

.. code-block:: python

    from dataclasses import dataclass
    from aioscraper import AIOScraper, Request, SendRequest


    scraper = AIOScraper()


    @dataclass
    class Config:
        github_token: str
        api_base_url: str


    class MetricsClient:
        """Send metrics to monitoring system"""

        async def counter(self, metric: str, value: float = 1.0):
            print(f"Metric: {metric} = {value}")

        async def close(self): ...


    @dataclass(slots=True)
    class RepoStats:
        name: str
        stars: int


    # Entry point: receives injected config dependency
    @scraper
    async def scrape(send_request: SendRequest, config: Config):
        """Scraper entry point with injected config"""
        await send_request(
            Request(
                url=f"{config.api_base_url}/repos/python/cpython",
                headers={"Authorization": f"token {config.github_token}"},
            )
        )


    # Middleware: receives injected metrics dependency
    @scraper.middleware("inner")
    async def start_request_middleware(metrics: MetricsClient):
        """Track when request starts"""
        await metrics.counter("request_started")


    @scraper.middleware("response")
    async def end_request_middleware(metrics: MetricsClient):
        """Track when request completes successfully"""
        await metrics.counter("request_ended")


    @scraper.middleware("exception")
    async def end_request_exc_middleware(metrics: MetricsClient):
        """Track when request fails with exception"""
        await metrics.counter("request_ended")


    # Lifespan: setup dependencies and cleanup
    @scraper.lifespan
    async def lifespan(scraper: AIOScraper):
        """
        Setup phase: create and register dependencies.
        Teardown phase: cleanup resources.
        """
        # Create resources
        config = Config(github_token="ghp_xxxx", api_base_url="https://api.github.com")
        metrics = MetricsClient()

        # Register dependencies - will be injected by parameter names
        scraper.add_dependencies(config=config, metrics=metrics)

        yield  # Scraper runs here

        # Cleanup
        await metrics.close()


Dependency injection rules
---------------------------

1. **Name-based matching**: Dependencies are injected by matching parameter names to registered keys (``config: Config`` matches ``add_dependencies(config=...)`` by the name ``config``)

2. **Built-in dependencies**: Some dependencies are always available:

   - ``send_request: SendRequest`` - schedule new requests
   - ``pipeline: Pipeline`` - send items to pipelines

3. **No dependency found**: If a parameter has no default and no matching dependency, raises an error

Best practices
--------------

1. **Use lifespan for setup/teardown**: Register dependencies in ``@scraper.lifespan`` to ensure proper cleanup

2. **Keep dependencies simple**: Inject services/clients, not raw data

3. **Test with mocks**: Dependency injection makes testing easy - just register mock objects

   .. code-block:: python

      # In tests
      mock_db = MockDatabase()
      scraper.add_dependencies(db_pool=mock_db)
