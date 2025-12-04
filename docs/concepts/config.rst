Configuration
=============

`aioscraper` ships sane defaults but exposes configuration for sessions, scheduling, execution, and pipeline dispatching.

You can build a :class:`Config <aioscraper.config.Config>` and pass it into :meth:`AIOScraper.start <aioscraper.scraper.core.AIOScraper.start>`, or override values via environment variables (see :doc:`/cli`). The CLI reads well-known environment variables (for example ``SESSION_REQUEST_TIMEOUT``, ``SCHEDULER_CONCURRENT_REQUESTS``, ``EXECUTION_TIMEOUT``, ``PIPELINE_STRICT``) and applies them before launching the scraper.


.. code-block:: python

    import logging
    from aioscraper import AIOScraper
    from aioscraper.config import Config, SessionConfig, SchedulerConfig, ExecutionConfig, PipelineConfig

    config = Config(
        session=SessionConfig(timeout=20, delay=0.05, ssl=True),
        scheduler=SchedulerConfig(concurrent_requests=32, pending_requests=4, close_timeout=0.5),
        execution=ExecutionConfig(
            timeout=60,
            shutdown_timeout=0.5,
            shutdown_check_interval=0.1,
            log_level=logging.WARNING,
        ),
        pipeline=PipelineConfig(strict=False),
    )


    async def main():
        async with AIOScraper() as scraper:
            await scraper.start(config)



.. autoclass:: aioscraper.config.Config
   :members:
   :no-index:

.. autoclass:: aioscraper.config.SessionConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.SchedulerConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.ExecutionConfig
   :members:
   :no-index:

.. autoclass:: aioscraper.config.PipelineConfig
   :members:
   :no-index:
