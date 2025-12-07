Pipelines
=========

Pipelines are ordered processors for your scraped items. Items are routed by their Python type: register pipelines against the item class and the dispatcher will use ``type(item)`` to find them. Add pipelines with ``scraper.pipeline.add`` or decorate pipeline classes with ``@scraper.pipeline(ItemType, *args, **kwargs)``; wrap their flow with middleware decorators.

Core
----
- Implement the :class:`BasePipeline <aioscraper.types.pipeline.BasePipeline>` protocol: provide ``put_item`` (persist/transform/fan out and return the item) and ``close`` for cleanup.
- Pipelines are keyed by item type; every pipeline registered for that type runs sequentially.
- Missing pipeline handling is controlled by ``PipelineConfig.strict`` (defaults to raising; set ``PIPELINE_STRICT=false`` to warn and continue).
- ``scraper.pipeline.add(...)`` adds one or more pipeline instances for a given item type.
- ``@scraper.pipeline(ItemType, *args, **kwargs)`` is a convenient decorator that instantiates the pipeline class and registers it for you (handy when the pipeline needs constructor arguments).


.. code-block:: python

    from dataclasses import dataclass
    from aioscraper import AIOScraper, Response, Pipeline

    scraper = AIOScraper()


    @dataclass(slots=True)
    class Article:
        title: str


    @scraper.pipeline(Article)
    class PrintPipeline:
        async def put_item(self, item: Article) -> Article:
            print("store:", item.title)
            return item

        async def close(self): ...


    async def callback(response: Response, pipeline: Pipeline):
        await pipeline(Article(title=(await response.json())["title"]))


Middlewares around pipelines
----------------------------
Pipeline middlewares let you step in before the first pipeline sees an item and after the last one finishes.
Use ``@scraper.pipeline.middleware("pre", ItemType)`` to normalize or enrich items on the way in, and ``@scraper.pipeline.middleware("post", ItemType)`` to finalize, log, or fan out results on the way out. 

Global middlewares registered via ``@scraper.pipeline.global_middleware`` wrap the entire chain for every item type; they work like FastAPI-style wrappers that accept injected dependencies and must ``await call_next(item)`` to keep the item moving. 

If you need to bail out of a pre/post stage, raise :class:`StopMiddlewareProcessing <aioscraper.exceptions.StopMiddlewareProcessing>` to skip the remaining middlewares in that stage but continue the rest of the flow, or raise :class:`StopItemProcessing <aioscraper.exceptions.StopItemProcessing>` to stop processing the current item altogether.

.. code-block:: python

   @scraper.pipeline.middleware("pre", Article)
   async def pre_process(item: Article) -> Article:
       ...

   @scraper.pipeline.middleware("post", Article)
   async def post_process(item: Article) -> Article:
       ...

   @scraper.pipeline.global_middleware
   def wrap_pipeline(db):
       async def middleware(call_next, item):
           db.log("start")
           item = await call_next(item)
           db.log("end")
           return item

       return middleware

Flow
-------------------
Picture the flow as nested wrappers (matryoshka style): global middlewares form the outer shells around the per-type chain. If you’ve used FastAPI middleware, it’s the same shape: a wrapper receives ``call_next`` and must ``await call_next(item)`` to keep the item moving.

.. code-block:: text

   global mw 1
      global mw 2
        global mw 3
          pre middlewares -> pipelines -> post middlewares
        global mw 3
      global mw 2
   global mw 1

When you call ``await pipeline(item)``:

- The dispatcher picks the container by ``type(item)``; if none is registered it raises or warns depending on ``PipelineConfig.strict``.
- Global middlewares run outer-to-inner. Each wrapper does its work and awaits ``call_next(item)`` to keep going; the final result bubbles back out through them in reverse order.
- Inside the core chain: run all pre-middlewares in registration order (each can mutate/replace the item).
- Run each pipeline instance in order; each must return the (possibly mutated) item for the next step.
- Run all post-middlewares in registration order.
- The returned item is whatever the last post-middleware (or pipeline, if no posts) produced.
