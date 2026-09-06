aioscraper
==========

**An async Python framework for collecting data from APIs.**

.. warning::
   Beta status: APIs and behavior still change between releases, so pin the version.

You write requests and response handlers. aioscraper queues the requests, limits concurrency, and
retries failed attempts. It has no selectors and no crawling engine - parse the response however you
like, with BeautifulSoup or anything else.

It is worth reaching for when one process has to keep hundreds or thousands of requests in flight
and you would otherwise be writing that machinery yourself. For a handful of requests, use
``aiohttp`` or ``httpx`` directly.

What you get
------------

- Plain asyncio on top of a pluggable HTTP client (``aiohttp``, ``httpx`` or ``httpx2``), so a
  scraper can also run inside an async service you already have
- Callbacks handle responses and can pass extracted items to pipelines for processing or storage;
  middleware runs around each stage
- A priority queue with a global concurrency limit, and a queue size that blocks the entrypoint once
  too many requests are waiting
- Retries with configurable backoff, and a configurable delay between requests, applied per group of
  targets (by hostname, or by a key of your own)
- Optional adaptive rate limiting: the delay grows after configured errors and shrinks after
  consecutive successful requests
- A small API that stays testable: explicit dependencies, no global state


.. toctree::
   :maxdepth: 2
   :caption: Contents:

   installation
   quickstart
   backends
   benchmarks
   cli

.. toctree::
   :maxdepth: 2
   :caption: Concepts:

   concepts/callbacks
   concepts/pipelines
   concepts/middlewares
   concepts/wiring
   concepts/lifespan
   concepts/config

.. toctree::
   :maxdepth: 2
   :caption: Reference:

   api
   compatibility
   changelog
   Contributing <contributing>

.. toctree::
   :maxdepth: 2
   :caption: Project Links:

   GitHub <https://github.com/darkstussy/aioscraper>
   PyPI <https://pypi.org/project/aioscraper>
