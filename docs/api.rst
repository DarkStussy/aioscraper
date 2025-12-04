API
=============

Core
----

.. autoclass:: aioscraper.scraper.core.AIOScraper
   :members:


Configuration
-------------

.. autoclass:: aioscraper.config.Config
.. autoclass:: aioscraper.config.SessionConfig
.. autoclass:: aioscraper.config.SchedulerConfig
.. autoclass:: aioscraper.config.ExecutionConfig
.. autoclass:: aioscraper.config.PipelineConfig

Types
-----

.. autoclass:: aioscraper.types.session.Request
.. autoclass:: aioscraper.types.session.Response
.. autoclass:: aioscraper.types.session.BasicAuth
.. autoclass:: aioscraper.types.pipeline.BaseItem
.. autoclass:: aioscraper.types.pipeline.Pipeline
.. autoclass:: aioscraper.types.pipeline.PipelineMiddleware

Session
-------

.. autoclass:: aioscraper.session.base.BaseSession
.. autoclass:: aioscraper.session.aiohttp.AiohttpSession

Pipeline
--------

.. autoclass:: aioscraper.pipeline.base.BasePipeline
.. autoclass:: aioscraper.pipeline.dispatcher.PipelineDispatcher

Execution
---------

.. autoclass:: aioscraper.scraper.executor.ScraperExecutor
.. autoclass:: aioscraper.scraper.request_manager.RequestManager

Exceptions
----------

.. autoclass:: aioscraper.exceptions.AIOScraperException
.. autoclass:: aioscraper.exceptions.ClientException
.. autoclass:: aioscraper.exceptions.HTTPException
.. autoclass:: aioscraper.exceptions.PipelineException
.. autoclass:: aioscraper.exceptions.StopMiddlewareProcessing
.. autoclass:: aioscraper.cli.exceptions.CLIError
