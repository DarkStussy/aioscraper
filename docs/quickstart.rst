Quickstart
==========

Build your first API data collector in minutes.
You'll fetch data from GitHub's REST API, extract repository stats, aggregate them in a pipeline, and run everything from the CLI.

Before you start, install ``aioscraper`` with an HTTP backend - see :doc:`installation` for details.

Create your first scraper
-------------------------

Save this as ``scraper.py``:

.. code-block:: python

   import logging
   from aioscraper import AIOScraper, Request, Response, SendRequest, Pipeline
   from dataclasses import dataclass

   logger = logging.getLogger("github_repos")
   scraper = AIOScraper()


   @dataclass(slots=True)
   class RepoStats:
       """Data model for extracted repository stats."""
       name: str
       stars: int
       language: str


    # this decorator registers this pipeline to handle RepoStats items
    @scraper.pipeline(RepoStats)
    class StatsPipeline:
        """Pipeline for processing extracted repository data."""

        def __init__(self):
            self.total_stars = 0

        async def put_item(self, item: RepoStats) -> RepoStats:
            """
            Called for each extracted item.

            This is where you'd:
            - Save to database
            - Send to message queue
            - Perform validation/transformation
            - Aggregate statistics
            """
            self.total_stars += item.stars
            logger.info("✓ %s: ⭐ %s (%s)", item.name, item.stars, item.language)
            return item

        async def close(self):
            """
            Called when scraper shuts down.

            Use for:
            - Final aggregations
            - Closing database connections
            - Cleanup operations
            """
            logger.info("Total stars collected: %s", self.total_stars)


    # this decorator marks this as the scraper's entry point.
    @scraper
    async def get_repos(send_request: SendRequest):
        """
        Entry point: defines what to scrape.

        Receives send_request - a function to schedule HTTP requests.
        """
        repos = (
            "django/django",
            "fastapi/fastapi",
            "pallets/flask",
            "encode/httpx",
            "aio-libs/aiohttp",
        )

        for repo in repos:
            await send_request(
                Request(
                    url=f"https://api.github.com/repos/{repo}",  # API endpoint
                    callback=parse_repo,  # Success handler
                    errback=on_failure,  # Error handler (network failures, timeouts)
                    cb_kwargs={"repo": repo},  # Additional arguments to pass to callbacks
                    headers={"Accept": "application/vnd.github+json"},  # Required by GitHub API
                )
            )


    async def parse_repo(response: Response, pipeline: Pipeline):
        """
        Success callback: parse response and extract data.

        The `pipeline` dependency is automatically injected by aioscraper.
        """
        data = await response.json()  # Parse JSON response from API
        await pipeline(  # Send extracted item to pipeline
            RepoStats(
                name=data["full_name"],
                stars=data["stargazers_count"],
                language=data.get("language", "Unknown"),
            )
        )


   async def on_failure(exc: Exception, repo: str):
       """
       Error callback: handle request/processing failures.

       Use for:
       - Logging errors
       - Sending alerts
       - Custom retry logic
       """
       logger.error("%s: cannot parse response: %s", repo, exc)

Run it
------

Execute your scraper from the command line:

.. code-block:: bash

   aioscraper scraper --concurrent-requests=4

The ``--concurrent-requests`` flag controls how many requests run simultaneously. Without it, the default concurrency limit of 64 applies.

What happens when it runs
-------------------------

1. **CLI loads the module**: The ``aioscraper`` command finds your ``scraper.py`` file and locates the ``AIOScraper`` instance.

2. **Entry point executes**: Your ``get_repos()`` function runs and schedules 5 requests to GitHub's API.

3. **Concurrent execution**: All 5 requests execute concurrently (limited by ``--concurrent-requests``). The async HTTP client makes non-blocking calls, so responses can arrive in any order.

4. **Callbacks process responses**:

   - If successful: ``parse_repo()`` extracts data and sends it to the pipeline
   - If failed: ``on_failure()`` logs the error

5. **Pipeline processes items**: ``StatsPipeline.put_item()`` runs for each ``RepoStats`` item, aggregating the total stars.

6. **Cleanup on shutdown**: After all requests complete, ``StatsPipeline.close()`` prints the total stars collected.

Customize for your use case
----------------------------

**Change the API**
   Replace GitHub API with your target API:

   .. code-block:: python

      await send_request(
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

      async def parse_page(response: Response, send_request: SendRequest, page: int):
          data = await response.json()
          # Process items...

          if data.get("next_page"):
              await send_request(
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

   # Enable retries for transient failures
   export RETRY_ENABLED=true
   export RETRY_MAX_ATTEMPTS=3

   # Enable rate limiting
   export RATE_LIMIT_ENABLED=true
   export RATE_LIMIT_DEFAULT_INTERVAL=1.0

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
