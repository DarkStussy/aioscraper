API
===

Core
----

.. autoclass:: aioscraper.core.scraper.AIOScraper
   :members:
   :special-members: __call__

.. autofunction:: aioscraper.core.runner.run_scraper

.. autoclass:: aioscraper.core.errors.RunResult
   :members:

.. autoclass:: aioscraper.core.errors.ScraperError

.. autofunction:: aioscraper.compiled

.. autodata:: aioscraper.core.scraper.Lifespan
.. autodata:: aioscraper.types.scraper.Scraper


Configuration
-------------

.. autoclass:: aioscraper.config.models.Config
.. autoclass:: aioscraper.config.models.SessionConfig
.. autoclass:: aioscraper.config.models.RequestRetryConfig
.. autoclass:: aioscraper.config.models.SchedulerConfig
.. autoclass:: aioscraper.config.models.ExecutionConfig
.. autoclass:: aioscraper.config.models.PipelineConfig
.. autoclass:: aioscraper.config.models.HttpBackend
.. autoclass:: aioscraper.config.models.BackoffStrategy
.. autoclass:: aioscraper.config.models.RateLimitConfig
.. autoclass:: aioscraper.config.models.AdaptiveRateLimitConfig
.. autoclass:: aioscraper.config.models.ErrorPolicy
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
.. autoclass:: aioscraper.core.session.httpx2.Httpx2Session
.. autoclass:: aioscraper.core.session.httpx2.Httpx2RequestContextManager
   :special-members: __aenter__, __aexit__
.. autofunction:: aioscraper.core.session.factory.get_sessionmaker
.. autoclass:: aioscraper.types.session.Request
.. autoclass:: aioscraper.types.session.Response
.. autoclass:: aioscraper.types.session.BasicAuth
.. autoclass:: aioscraper.types.session.File
.. autodata:: aioscraper.types.session.SendRequest
.. autodata:: aioscraper.types.session.QueryParams
.. autodata:: aioscraper.types.session.RequestCookies
.. autodata:: aioscraper.types.session.RequestHeaders
.. autodata:: aioscraper.types.session.RequestFiles

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
.. autodata:: aioscraper.types.pipeline.ItemHandler
.. autodata:: aioscraper.types.pipeline.PipelineMiddlewareStage
.. autodata:: aioscraper.types.pipeline.GlobalPipelineMiddlewareFactory

Execution
---------

.. autoclass:: aioscraper.core.executor.ScraperExecutor
.. autoclass:: aioscraper.core.request_manager.RequestManager
.. autoclass:: aioscraper.core.rate_limiter.RateLimitManager
.. autoclass:: aioscraper.core.rate_limiter.RequestGroup
.. autoclass:: aioscraper.core.rate_limiter.AdaptiveStrategy
.. autoclass:: aioscraper.core.rate_limiter.RequestOutcome
.. autoclass:: aioscraper.core.rate_limiter.AdaptiveMetrics

Middleware
----------

.. autoclass:: aioscraper.types.middleware.RequestHandler
   :special-members: __call__
.. autoclass:: aioscraper.types.middleware.RequestMiddleware
   :special-members: __call__
.. autodata:: aioscraper.types.middleware.RequestMiddlewareFactory

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
.. autoclass:: aioscraper.exceptions.TransportError
.. autoclass:: aioscraper.exceptions.TransportTimeout
.. autoclass:: aioscraper.exceptions.ConnectionFailed
.. autoclass:: aioscraper.exceptions.DNSError
.. autoclass:: aioscraper.exceptions.ProxyError
.. autoclass:: aioscraper.exceptions.TLSError
.. autoclass:: aioscraper.exceptions.ResponseTooLarge
.. autoclass:: aioscraper.exceptions.StreamConsumed
.. autoclass:: aioscraper.exceptions.UnsupportedRequestOption
.. autoclass:: aioscraper.exceptions.PipelineException
.. autoclass:: aioscraper.exceptions.StopItemProcessing
.. autoclass:: aioscraper.exceptions.StopMiddlewareProcessing
.. autoclass:: aioscraper.exceptions.InvalidRequestData
.. autoclass:: aioscraper.exceptions.CLIError
.. autoclass:: aioscraper.exceptions.ConfigValidationError
