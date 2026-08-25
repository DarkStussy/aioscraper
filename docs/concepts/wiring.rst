Wiring scrapers and dependencies
================================

Shared resources - database clients, API clients, settings objects - are registered once on the scraper and reach your scrapers, callbacks, errbacks, middleware factories and pipeline middleware factories as arguments.

How it works
------------

1. Register with ``add_dependencies(**kwargs)``, usually from a lifespan.
2. Name the ones you want as parameters of your function.
3. `aioscraper` inspects the signature and passes the ones whose names match.

Matching is **by parameter name only** - the type hint is documentation, not part of the lookup. A parameter whose name matches nothing registered is simply not passed, so a parameter without a default makes the call fail with ``TypeError``.

Scrapers
--------
:meth:`__call__ <aioscraper.core.scraper.AIOScraper.__call__>`: Register one async callable as an entry point and return it, so it works as a decorator. Call it again for each further entry point; they all run concurrently.

Dependencies
------------
:meth:`add_dependencies <aioscraper.core.scraper.AIOScraper.add_dependencies>`: Register objects under the names they will be injected by. Calling it again adds to what is registered, and reuses a name to replace it.

Example
-------

.. code-block:: python

    from dataclasses import dataclass
    from aioscraper import AIOScraper, Request, ScheduleRequest


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
    async def scrape(schedule_request: ScheduleRequest, config: Config):
        """Scraper entry point with injected config"""
        await schedule_request(
            Request(
                url=f"{config.api_base_url}/repos/python/cpython",
                headers={"Authorization": f"token {config.github_token}"},
            )
        )


    # Middleware: factory receives injected metrics dependency
    @scraper.middleware
    def request_metrics(metrics: MetricsClient):
        async def middleware(call_next, request):
            await metrics.counter("request_started")
            try:
                response = await call_next(request)
            except Exception:
                await metrics.counter("request_ended")
                raise
            await metrics.counter("request_ended")
            return response

        return middleware


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


Rules
-----

1. **Names, not types**: ``config: Config`` is injected because ``add_dependencies(config=...)`` used the name ``config``. Renaming the parameter breaks the match; changing the annotation does not.

2. **Always available**: three dependencies are registered by the framework itself:

   - ``schedule_request: ScheduleRequest`` - schedule further requests
   - ``pipeline: Pipeline`` - send items into the pipelines
   - ``config: Config`` - the run's configuration, unless you registered your own ``config``

   ``schedule_request`` was called ``send_request`` before, and ``ScheduleRequest`` was
   ``SendRequest``. Both old names still work - the same dependency is injected under either
   parameter name - and are removed in 1.0.

3. **Callbacks also get the request**: ``response`` and ``request`` reach a callback, ``exc`` and ``request`` an errback, alongside anything in ``Request.cb_kwargs``.

4. **Nothing matched**: an unmatched parameter is left out of the call, so give it a default unless you mean the call to fail.

5. **Reserved names**: ``request``, ``response``, ``exc``, ``schedule_request``, ``send_request`` and ``pipeline`` are the framework's. ``add_dependencies`` raises ``ValueError`` on them, and so does a ``Request`` whose ``cb_kwargs`` takes one of the first three. ``config`` is the exception: registering it replaces the framework's for the whole run. Precedence, highest to lowest: framework callback arguments, ``cb_kwargs``, injected dependencies.

Registering in a lifespan is what ties setup to teardown; see :doc:`lifespan`. In tests, ``add_dependencies`` is also how you swap a client for a fake:

.. code-block:: python

   mock_db = MockDatabase()
   scraper.add_dependencies(db_pool=mock_db)
