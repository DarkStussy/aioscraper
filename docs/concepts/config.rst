Configuration
=============

`aioscraper` ships sane defaults but exposes configuration for sessions, scheduling, and execution. You can pass a :class:`aioscraper.config.Config` when creating :class:`aioscraper.AIOScraper`, or override values via CLI flags and environment variables (see :doc:`/cli`). The CLI reads well-known environment variables (for example ``SESSION_REQUEST_TIMEOUT``, ``SCHEDULER_CONCURRENT_REQUESTS``, ``EXECUTION_TIMEOUT``) and applies them before launching the scraper.

Config blocks
-------------
- ``SessionConfig`` — request timeout, delay between requests, SSL toggle.
- ``SchedulerConfig`` — concurrency limits, pending queue size, scheduler shutdown timeout.
- ``ExecutionConfig`` — global run timeout, graceful shutdown timing, log level used on timeouts.

Example
-------

.. code-block:: python

   import logging
   from aioscraper import AIOScraper
   from aioscraper.config import Config, SessionConfig, SchedulerConfig, ExecutionConfig

   config = Config(
       session=SessionConfig(timeout=20, delay=0.05, ssl=True),
       scheduler=SchedulerConfig(concurrent_requests=32, pending_requests=4, close_timeout=0.5),
       execution=ExecutionConfig(
           timeout=60,
           shutdown_timeout=0.5,
           shutdown_check_interval=0.1,
           log_level=logging.WARNING,
       ),
   )

   scraper = AIOScraper(config=config)
