Pipelines
=========

Pipelines are ordered processors for your scraped items. Each item declares which pipeline set to use via ``pipeline_name``; the dispatcher routes items to matching pipelines.

Core
----
- Implement :class:`BasePipeline.put_item <aioscraper.pipeline.base.BasePipeline.put_item>` to persist, transform, or fan out data.
- Items must expose ``pipeline_name`` (property or attribute) so the dispatcher can route them.
- Multiple pipelines can share the same name; all matching pipelines run sequentially.
- Missing pipeline handling is controlled by ``PipelineConfig.strict`` (defaults to raising; set ``PIPELINE_STRICT=false`` to warn and continue).
- :meth:`add_pipelines <aioscraper.scraper.core.AIOScraper.add_pipelines>` registers one or more pipeline instances for a given ``pipeline_name``.


.. code-block:: python

    from dataclasses import dataclass
    from aioscraper import AIOScraper
    from aioscraper.pipeline import BasePipeline
    from aioscraper.types import Pipeline

    scraper = AIOScraper()


    @dataclass(slots=True)
    class Article:
        title: str

        @property
        def pipeline_name(self) -> str:
            return "articles"


    class PrintPipeline(BasePipeline[Article]):
        async def put_item(self, item: Article) -> Article:
            print("store:", item.title)
            return item


    scraper.add_pipelines("articles", PrintPipeline())


    async def callback(response, pipeline: Pipeline):
        await pipeline(Article(title=response.json()["title"]))


Middlewares around pipelines
----------------------------
- Pipeline middlewares let you hook into the item flow before the first pipeline and after the last one. They receive the current item instance and must return it (mutated or replaced).
- Register pre-middlewares with :meth:`add_pipeline_pre_middlewares <aioscraper.scraper.core.AIOScraper.add_pipeline_pre_middlewares>` to prepare or normalize the item before any pipeline sees it.
- Register post-middlewares with :meth:`add_pipeline_post_middlewares <aioscraper.scraper.core.AIOScraper.add_pipeline_post_middlewares>` to finalize or log the item after all pipelines finish.

.. code-block:: python

   async def pre_process(item: Article) -> Article:
       ...

   async def post_process(item: Article) -> Article:
       ...

   scraper.add_pipeline_pre_middlewares("articles", pre_process)
   scraper.add_pipeline_post_middlewares("articles", post_process)

Flow (per ``pipeline_name``)

1. Run every pre-middleware in registration order (each awaits the previous one).
2. Invoke each pipeline in order.
3. Run every post-middleware in registration order.
4. Return the (possibly mutated) item instance.
