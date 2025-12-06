Pipelines
=========

Pipelines are ordered processors for your scraped items. Items are routed by their Python type: register pipelines against the item class and the dispatcher will use ``type(item)`` to find them. Add pipelines with ``scraper.pipeline.add`` or decorate pipeline classes with ``@scraper.pipeline(ItemType, *args, **kwargs)``; wrap their flow with middleware decorators.

Core
----
- Implement :class:`BasePipeline.put_item <aioscraper.types.pipeline.BasePipeline.put_item>` to persist, transform, or fan out data.
- Pipelines are keyed by item type; every pipeline registered for that type runs sequentially.
- Missing pipeline handling is controlled by ``PipelineConfig.strict`` (defaults to raising; set ``PIPELINE_STRICT=false`` to warn and continue).
- ``scraper.pipeline.add(...)`` adds one or more pipeline instances for a given item type.
- ``@scraper.pipeline(ItemType, *args, **kwargs)`` instantiates and registers a pipeline class (useful when you need constructor args).


.. code-block:: python

    from dataclasses import dataclass
    from aioscraper import AIOScraper
    from aioscraper.types import Response, Pipeline

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
        await pipeline(Article(title=response.json()["title"]))


Middlewares around pipelines
----------------------------
- Pipeline middlewares let you hook into the item flow before the first pipeline and after the last one. They receive the current item instance and must return it (mutated or replaced).
- Register pre-middlewares with ``@scraper.pipeline.middleware("pre", ItemType)`` to prepare or normalize the item before any pipeline sees it.
- Register post-middlewares with ``@scraper.pipeline.middleware("post", ItemType)`` to finalize or log the item after all pipelines finish.
- Register global middlewares with ``@scraper.pipeline.global_middleware()`` to wrap the whole pipeline execution for all item types. Signature: ``async def middleware(item, process_item, **deps)`` where ``process_item`` continues the pipeline chain (and other keyword args are injected dependencies).
- Raise :class:`StopMiddlewareProcessing <aioscraper.exceptions.StopMiddlewareProcessing>` to stop remaining middlewares in the current phase (pre/post) but continue the rest of the pipeline flow.
- Raise :class:`StopItemProcessing <aioscraper.exceptions.StopItemProcessing>` to stop processing the current item entirely (skip remaining middlewares and pipelines).

.. code-block:: python

   @scraper.pipeline.middleware("pre", Article)
   async def pre_process(item: Article) -> Article:
       ...

   @scraper.pipeline.middleware("post", Article)
   async def post_process(item: Article) -> Article:
       ...

   @scraper.pipeline.global_middleware()
   async def wrap_pipeline(item: Article, process_item, db) -> Article:
       db.log("start")
       item = await process_item(item)  # runs pre -> pipelines -> post
       db.log("end")
       return item

Flow (per item type):

1. Run global middlewares as a wrapper chain (applied to every item type); each calls ``process_item`` to continue.
2. Inside, run every pre-middleware in registration order (each awaits the previous one).
3. Invoke each pipeline in order.
4. Run every post-middleware in registration order.
5. Return the (possibly mutated) item instance.
