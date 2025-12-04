aioscraper
==========

Orchestrates asynchronous scrapers, middlewares, and pipelines for high-volume, low-latency web requests.

You define scraping tasks that queue requests. A scheduler dispatches them with your chosen concurrency and priorities. HTTP clients perform the calls and return responses. Callbacks handle those responses and hand items off to pipelines, which process items in order and then shut down cleanly.

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

.. toctree::
   :maxdepth: 2
   :caption: Project Links:

   GitHub <https://github.com/darkstussy/aioscraper>
   PyPI <https://pypi.org/project/aioscraper>
