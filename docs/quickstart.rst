Quickstart
==========

A first collector: fetch repository stats from GitHub's REST API, aggregate them in a pipeline, run it from the CLI.

Install ``aioscraper`` with an HTTP backend first - see :doc:`installation`.

Create your first scraper
-------------------------

Save this as ``scraper.py``:

.. code-block:: python

   import logging
   from aioscraper import AIOScraper, Request, Response, ScheduleRequest, Pipeline
   from dataclasses import dataclass

   logger = logging.getLogger("github_repos")
   scraper = AIOScraper()


   @dataclass(slots=True)
   class RepoStats:
       name: str
       stars: int
       language: str


   # registers the pipeline that handles RepoStats items
   @scraper.pipeline(RepoStats)
   class StatsPipeline:
       def __init__(self):
           self.total_stars = 0

       async def put_item(self, item: RepoStats) -> RepoStats:
           # runs once per extracted item: store it, queue it, validate it, or aggregate as here
           self.total_stars += item.stars
           logger.info("✓ %s: ⭐ %s (%s)", item.name, item.stars, item.language)
           return item

       async def close(self):
           # runs once when the scraper stops: flush buffers, close connections, report totals
           logger.info("Total stars collected: %s", self.total_stars)


   # registers an entry point; schedule_request is injected by parameter name
   @scraper
   async def get_repos(schedule_request: ScheduleRequest):
       repos = (
           "django/django",
           "fastapi/fastapi",
           "pallets/flask",
           "encode/httpx",
           "aio-libs/aiohttp",
       )

       for repo in repos:
           await schedule_request(
               Request(
                   url=f"https://api.github.com/repos/{repo}",
                   callback=parse_repo,  # runs on a response with a status below 400
                   errback=on_failure,  # runs on anything else: 4xx/5xx, timeouts, connection failures
                   cb_kwargs={"repo": repo},  # extra arguments for both of them
                   headers={"Accept": "application/vnd.github+json"},  # required by the GitHub API
               )
           )


   async def parse_repo(response: Response, pipeline: Pipeline):
       # the body has to be read here: the connection is released when the callback returns
       data = await response.json()
       await pipeline(
           RepoStats(
               name=data["full_name"],
               stars=data["stargazers_count"],
               language=data.get("language", "Unknown"),
           )
       )


   async def on_failure(exc: Exception, repo: str):
       logger.error("%s: cannot parse response: %s", repo, exc)

Run it
------

Execute your scraper from the command line:

.. code-block:: bash

   aioscraper scraper --concurrent-requests=4

``--concurrent-requests`` caps how many requests are in flight at once; the default is 64.

What happens when it runs
-------------------------

1. The ``aioscraper`` command imports ``scraper.py`` and takes the ``scraper`` attribute from it.
2. ``get_repos()`` runs and queues 5 requests. ``schedule_request()`` returns as soon as a request is accepted - it does not wait for the response.
3. The framework dispatches them, up to ``--concurrent-requests`` at a time, so responses arrive in no particular order.
4. ``parse_repo()`` runs for each response, ``on_failure()`` for each failure that retries did not recover from.
5. ``StatsPipeline.put_item()`` runs for every ``RepoStats`` handed to ``pipeline()``. Callbacks run concurrently, so their calls into the pipeline can overlap - what runs in order is the chain within one call.
6. Once every request has finished, ``StatsPipeline.close()`` runs and the process exits.

Customize for your use case
----------------------------

**Change the API**
   Replace GitHub API with your target API:

   .. code-block:: python

      await schedule_request(
          Request(
              url="https://api.example.com/products",
              callback=parse_product,
              headers={"Authorization": "Bearer YOUR_TOKEN"},
          )
      )

**Add query parameters**
   Use the ``params`` argument:

   .. code-block:: python

      Request(
          url="https://api.example.com/search",
          params={"q": "python", "limit": 100},
          callback=parse_results,
      )

**Save to database**
   In ``put_item()``, use your ORM or database client:

   .. code-block:: python

      async def put_item(self, item: RepoStats) -> RepoStats:
          await self.db.execute(
              "INSERT INTO repos (name, stars, language) VALUES (?, ?, ?)",
              (item.name, item.stars, item.language)
          )
          return item

**Handle pagination**
   Send follow-up requests from callbacks:

   .. code-block:: python

      async def parse_page(response: Response, schedule_request: ScheduleRequest, page: int):
          data = await response.json()
          # Process items...

          if data.get("next_page"):
              await schedule_request(
                  Request(
                      url=data["next_page"],
                      callback=parse_page,
                      cb_kwargs={"page": page + 1},
                  )
              )

Production configuration
------------------------

For production use, configure retries, rate limiting, and concurrency via environment variables:

.. code-block:: bash

   # Retries are on by default; tune or turn them off
   export SESSION_RETRY_ATTEMPTS=3

   # Enable rate limiting
   export SESSION_RATE_LIMIT_ENABLED=true
   export SESSION_RATE_LIMIT_INTERVAL=1.0

   # Set concurrency
   export SCHEDULER_CONCURRENT_REQUESTS=10

   aioscraper scraper

See :doc:`cli` for all available configuration options.

Next steps
----------

- **Learn about pipelines**: See :doc:`concepts/pipelines` for advanced item processing, error handling, and multiple pipelines.
- **Add middlewares**: See :doc:`concepts/middlewares` for request/response transformation, auth, logging, and circuit breaking.
- **Manage resources**: See :doc:`concepts/lifespan` for setting up database connections, external services, and cleanup.
- **Dependency injection**: See :doc:`concepts/wiring` to inject custom dependencies into callbacks and pipelines.
- **Configuration**: See :doc:`concepts/config` for programmatic configuration and advanced settings.
