API
=============

Core
----

.. autoclass:: aioscraper.AIOScraper

Configuration
-------------

.. autoclass:: aioscraper.config.Config
.. autoclass:: aioscraper.config.SessionConfig
.. autoclass:: aioscraper.config.RequestConfig
.. autoclass:: aioscraper.config.SchedulerConfig
.. autoclass:: aioscraper.config.ExecutionConfig

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

.. autoclass:: aioscraper.exceptions.AIOScrapperException
.. autoclass:: aioscraper.exceptions.ClientException
.. autoclass:: aioscraper.exceptions.HTTPException
.. autoclass:: aioscraper.exceptions.RequestException
.. autoclass:: aioscraper.exceptions.PipelineException
.. autoclass:: aioscraper.exceptions.StopMiddlewareProcessing
