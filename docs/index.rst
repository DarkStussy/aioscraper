aioscraper
==========

**High-performance asynchronous Python framework for large-scale API data collection.**

.. warning::
   Beta status: APIs and behavior may change, so pin versions and expect occasional breakage while things stabilize.

What is aioscraper?
-------------------

aioscraper is an async Python framework designed for **mass data collection from APIs** and external services at scale.

**Built for:**

- Fetching data from hundreds/thousands of REST API endpoints concurrently
- Integrating multiple external services (payment gateways, analytics APIs, etc.)
- Building data aggregation pipelines from heterogeneous API sources
- Queue-based scraping workers consuming tasks from Redis/RabbitMQ
- Microservice fan-out requests with automatic rate limiting and retries

**NOT built for:**

- Parsing HTML/CSS (but nothing stops you from using BeautifulSoup if you want)
- Single API requests (use httpx or aiohttp directly)
- GraphQL or WebSocket scraping (different paradigm)

**Think:** "I need to fetch data from 10,000 product API endpoints" or "I need to poll 50 microservices every minute" → aioscraper is for you.

Key Features
------------

- **Async-first** core with pluggable HTTP backends (``aiohttp``/``httpx``) and ``aiojobs`` scheduling
- **Declarative flow**: requests → callbacks → pipelines, with middleware hooks at each stage
- **Priority queueing** plus configurable concurrency limits per group
- **Adaptive rate limiting** with EWMA + AIMD algorithm - automatically backs off on server overload
- **Small, explicit API** that is easy to test and compose with existing async applications


.. toctree::
   :maxdepth: 2
   :caption: Contents:

   installation
   quickstart
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
   changelog
   Contributing <contributing>

.. toctree::
   :maxdepth: 2
   :caption: Project Links:

   GitHub <https://github.com/darkstussy/aioscraper>
   PyPI <https://pypi.org/project/aioscraper>
