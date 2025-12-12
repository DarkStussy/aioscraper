API
===

Core
----

.. autoclass:: aioscraper.core.scraper.AIOScraper
   :members:
   :special-members: __call__

.. autofunction:: aioscraper.core.runner.run_scraper

.. autofunction:: aioscraper.compiled


Configuration
-------------

.. autoclass:: aioscraper.config.models.Config
.. autoclass:: aioscraper.config.models.SessionConfig
.. autoclass:: aioscraper.config.models.RequestRetryConfig
.. autoclass:: aioscraper.config.models.SchedulerConfig
.. autoclass:: aioscraper.config.models.ExecutionConfig
.. autoclass:: aioscraper.config.models.PipelineConfig
.. autoclass:: aioscraper.config.models.MiddlewareConfig
.. autoclass:: aioscraper.config.models.HttpBackend
.. autoclass:: aioscraper.config.models.BackoffStrategy
.. autoclass:: aioscraper.config.models.RateLimitConfig
.. autoclass:: aioscraper.config.models.AdaptiveRateLimitConfig
.. autofunction:: aioscraper.config.loader.load_config


Session
-------

.. autoclass:: aioscraper.core.session.base.BaseRequestContextManager
   :special-members: __aenter__, __aexit__
.. autoclass:: aioscraper.core.session.base.BaseSession
.. autoclass:: aioscraper.core.session.aiohttp.AiohttpSession
.. autoclass:: aioscraper.core.session.aiohttp.AiohttpRequestContextManager
   :special-members: __aenter__, __aexit__
.. autoclass:: aioscraper.core.session.httpx.HttpxSession
.. autoclass:: aioscraper.core.session.httpx.HttpxRequestContextManager
   :special-members: __aenter__, __aexit__
.. autofunction:: aioscraper.core.session.factory.get_sessionmaker
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

Middlewares
-----------

.. autoclass:: aioscraper.middlewares.retry.RetryMiddleware

Execution
---------

.. autoclass:: aioscraper.core.executor.ScraperExecutor
.. autoclass:: aioscraper.core.request_manager.RequestManager
.. autoclass:: aioscraper.core.rate_limiter.RateLimitManager
.. autoclass:: aioscraper.core.rate_limiter.RequestGroup
.. autoclass:: aioscraper.core.rate_limiter.AdaptiveStrategy
.. autoclass:: aioscraper.core.rate_limiter.RequestOutcome
.. autoclass:: aioscraper.core.rate_limiter.AdaptiveMetrics

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
