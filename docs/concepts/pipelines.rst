Pipelines
=========

Pipelines are where a scraped item goes after a callback produces it. Routing is by exact Python type: the dispatcher looks up ``type(item)``, so a subclass needs its own registration.

Core
----
- Implement the :class:`BasePipeline <aioscraper.types.pipeline.BasePipeline>` protocol: provide ``put_item`` (persist/transform/fan out and return the item) and ``close`` for cleanup.
- Pipelines are keyed by item type; every pipeline registered for that type runs sequentially.
- Missing pipeline handling is controlled by ``PipelineConfig.strict`` (defaults to raising; set ``PIPELINE_STRICT=false`` to warn and continue).
- ``scraper.pipeline.add(ItemType, *pipelines)`` registers instances you built yourself, which is what a pipeline needing a dependency takes.
- ``@scraper.pipeline(ItemType, *args, **kwargs)`` instantiates the decorated class with those arguments and registers the instance.


.. code-block:: python

    from dataclasses import dataclass
    from aioscraper import AIOScraper, Request, ScheduleRequest, Response, Pipeline, ItemHandler

    scraper = AIOScraper()


    # stands in for a real database client
    class DatabaseClient:
        async def connect(self):
            print("Connected to database")

        async def save_article(self, title: str, url: str):
            print(f"Saved: {title} -> {url}")

        async def close(self):
            print("Closed database connection")


    @dataclass(slots=True)
    class Article:
        title: str
        url: str


    class SaveArticlePipeline:
        def __init__(self, db: DatabaseClient):
            self.db = db

        async def put_item(self, item: Article) -> Article:
            await self.db.save_article(item.title, item.url)
            return item

        async def close(self):
            # the lifespan owns the client, so there is nothing to close here
            pass


    @scraper.lifespan
    async def lifespan(scraper: AIOScraper):
        db = DatabaseClient()
        await db.connect()

        # injected into callbacks/errbacks/middlewares under the name "db"
        scraper.add_dependencies(db=db)
        scraper.pipeline.add(Article, SaveArticlePipeline(db))

        try:
            yield  # the scraper runs here
        finally:
            await db.close()


    @scraper
    async def get_article(schedule_request: ScheduleRequest):
        await schedule_request(Request(url="https://api.article.com", callback=callback))


    async def callback(response: Response, pipeline: Pipeline):
        data = await response.json()
        await pipeline(Article(title=data["title"], url=response.url))



Middlewares around pipelines
----------------------------
Pipeline middlewares let you step in before the first pipeline sees an item and after the last one finishes.
Use ``@scraper.pipeline.middleware("pre", ItemType)`` to normalize or enrich items on the way in, and ``@scraper.pipeline.middleware("post", ItemType)`` to finalize, log, or fan out results on the way out.

Global middlewares registered via ``@scraper.pipeline.global_middleware`` wrap the entire chain for every item type. Such a middleware is a factory that receives injected dependencies and returns a wrapper, which must ``await handler(item)`` for the rest of the chain to run.

If you need to bail out of a pre/post stage, raise :class:`StopMiddlewareProcessing <aioscraper.exceptions.StopMiddlewareProcessing>` to skip the remaining middlewares in that stage but continue the rest of the flow, or raise :class:`StopItemProcessing <aioscraper.exceptions.StopItemProcessing>` to stop processing the current item altogether.

.. code-block:: python

   import logging
   from time import monotonic

   logger = logging.getLogger(__name__)


   @scraper.pipeline.middleware("pre", Article)
   async def strip_title(item: Article) -> Article:
       item.title = item.title.strip()
       return item

   @scraper.pipeline.middleware("post", Article)
   async def log_saved(item: Article) -> Article:
       logger.info("saved %s", item.url)
       return item

   @scraper.pipeline.global_middleware
   def time_items():
       async def middleware(handler: ItemHandler, item: Article) -> Article:
           started = monotonic()
           try:
               return await handler(item)
           finally:
               logger.info("%s took %.3fs", type(item).__name__, monotonic() - started)

       return middleware

Every middleware here returns the item: whatever a pre-middleware returns is what the pipelines
receive, and whatever the chain returns is what ``await pipeline(item)`` gives back. Returning
``None`` replaces the item with ``None`` for everything downstream.

Flow
-------------------
Global middlewares wrap everything, the innermost of them wrapping the per-type chain. They are
composed in registration order, so the **last** registered one ends up outermost - the opposite of
:doc:`request middlewares <middlewares>`, where the first is. A wrapper receives ``handler`` and must
``await handler(item)`` for the chain inside it to run.

.. code-block:: text

   global mw 3 (registered last)
      global mw 2
        global mw 1 (registered first)
          pre middlewares -> pipelines -> post middlewares
        global mw 1
      global mw 2
   global mw 3

When you call ``await pipeline(item)``:

- Global middlewares run outer-to-inner, before the item's type is looked at. A middleware that
  never awaits ``handler(item)`` keeps the type lookup from happening at all, and one that wraps the
  call in ``try/except`` also catches what that lookup raises.
- The dispatcher then picks the container by ``type(item)``; if none is registered it raises
  :class:`PipelineException <aioscraper.exceptions.PipelineException>` or warns and returns the item,
  depending on ``PipelineConfig.strict``.
- Inside the core chain: run all pre-middlewares in registration order (each can mutate/replace the item).
- Run each pipeline instance in order; each must return the (possibly mutated) item for the next step.
- Run all post-middlewares in registration order.
- The result travels back out through the global middlewares in reverse order. What ``pipeline()``
  returns is whatever the outermost one produced.
