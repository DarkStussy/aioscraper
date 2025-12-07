API
=============

Core
----

.. autoclass:: aioscraper.core.scraper.AIOScraper
   :members:
   :special-members: __call__

.. autofunction:: aioscraper.core.runner.run_scraper


Configuration
-------------

.. autoclass:: aioscraper.config.Config
.. autoclass:: aioscraper.config.SessionConfig
.. autoclass:: aioscraper.config.SchedulerConfig
.. autoclass:: aioscraper.config.ExecutionConfig
.. autoclass:: aioscraper.config.PipelineConfig
.. autoclass:: aioscraper.config.HttpBackend
.. autofunction:: aioscraper.config.load_config


Session
-------

.. autoclass:: aioscraper.session.base.BaseRequestContextManager
   :special-members: __aenter__, __aexit__
.. autoclass:: aioscraper.session.base.BaseSession
.. autoclass:: aioscraper.session.aiohttp.AiohttpSession
.. autoclass:: aioscraper.session.aiohttp.AiohttpRequestContextManager
   :special-members: __aenter__, __aexit__
.. autoclass:: aioscraper.session.httpx.HttpxSession
.. autoclass:: aioscraper.session.httpx.HttpxRequestContextManager
   :special-members: __aenter__, __aexit__
.. autofunction:: aioscraper.session.factory.get_sessionmaker
.. autoclass:: aioscraper.types.session.Request
.. autoclass:: aioscraper.types.session.Response
.. autoclass:: aioscraper.types.session.BasicAuth
.. autoclass:: aioscraper.types.session.File

Pipeline
--------

.. autoclass:: aioscraper.core.pipeline.PipelineDispatcher
.. autoclass:: aioscraper.types.pipeline.Pipeline
   :special-members: __call__
.. autoclass:: aioscraper.types.pipeline.BasePipeline
.. autoclass:: aioscraper.types.pipeline.PipelineMiddleware
   :special-members: __call__
.. autoclass:: aioscraper.types.pipeline.GlobalPipelineMiddleware
   :special-members: __call__

Execution
---------

.. autoclass:: aioscraper.core.executor.ScraperExecutor
.. autoclass:: aioscraper.core.request_manager.RequestManager

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
.. autoclass:: aioscraper.exceptions.CLIError
