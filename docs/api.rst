API
=============

Core
----

.. autoclass:: aioscraper.scraper.core.AIOScraper
   :members:
   :special-members: __call__

.. autofunction:: aioscraper.scraper.runner.run_scraper


Configuration
-------------

.. autoclass:: aioscraper.config.Config
.. autoclass:: aioscraper.config.SessionConfig
.. autoclass:: aioscraper.config.SchedulerConfig
.. autoclass:: aioscraper.config.ExecutionConfig
.. autoclass:: aioscraper.config.PipelineConfig
.. autofunction:: aioscraper.config.load_config


Session
-------

.. autoclass:: aioscraper.session.base.BaseRequestContextManager
.. autoclass:: aioscraper.session.base.BaseSession
.. autoclass:: aioscraper.session.aiohttp.AiohttpSession
.. autoclass:: aioscraper.session.aiohttp.AiohttpRequestContextManager
.. autoclass:: aioscraper.session.httpx.HttpxSession
.. autoclass:: aioscraper.session.httpx.HttpxRequestContextManager
.. autofunction:: aioscraper.session.factory.get_sessionmaker
.. autoclass:: aioscraper.types.session.Request
.. autoclass:: aioscraper.types.session.Response
.. autoclass:: aioscraper.types.session.BasicAuth
.. autoclass:: aioscraper.types.session.File

Pipeline
--------

.. autoclass:: aioscraper.scraper.pipeline.PipelineDispatcher
.. autoclass:: aioscraper.types.pipeline.Pipeline
.. autoclass:: aioscraper.types.pipeline.BasePipeline
.. autoclass:: aioscraper.types.pipeline.PipelineMiddleware
.. autoclass:: aioscraper.types.pipeline.GlobalPipelineMiddleware

Execution
---------

.. autoclass:: aioscraper.scraper.executor.ScraperExecutor
.. autoclass:: aioscraper.scraper.request_manager.RequestManager

Holders
-------

.. autoclass:: aioscraper.holders.middleware.MiddlewareHolder
   :members:
   :special-members: __call__

.. autoclass:: aioscraper.holders.pipeline.PipelineHolder
   :members:
   :special-members: __call__

Exceptions
----------

.. autoclass:: aioscraper.exceptions.AIOScraperException
.. autoclass:: aioscraper.exceptions.ClientException
.. autoclass:: aioscraper.exceptions.HTTPException
.. autoclass:: aioscraper.exceptions.PipelineException
.. autoclass:: aioscraper.exceptions.StopItemProcessing
.. autoclass:: aioscraper.exceptions.StopRequestProcessing
.. autoclass:: aioscraper.exceptions.StopMiddlewareProcessing
.. autoclass:: aioscraper.exceptions.InvalidRequestData
.. autoclass:: aioscraper.cli.exceptions.CLIError
