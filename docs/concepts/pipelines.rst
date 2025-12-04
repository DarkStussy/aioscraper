Pipelines
=========

Pipelines are ordered processors for your scraped items. Each item declares which pipeline set to use via ``pipeline_name``.

Core ideas
----------
- Implement :class:`aioscraper.pipeline.BasePipeline.put_item` to persist, transform, or fan out data.
- Items must expose ``pipeline_name`` (property or attribute) so the dispatcher can route them.
- Multiple pipelines can share the same name; all will run sequentially.
- Pre/post pipeline middlewares wrap processing for validation, enrichment, or auditing.

Example
-------

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
       async def put_item(self, item: Article) -> None:
           print("store:", item.title)

   async def validate(item: Article):
       if not item.title.strip():
           raise ValueError("empty title")

   async def mark_clean(item: Article):
       item.title = item.title.strip()

   scraper.add_pipeline("articles", PrintPipeline())
   scraper.add_pipeline_pre_processing_middlewares(validate)
   scraper.add_pipeline_post_processing_middlewares(mark_clean)

   async def callback(response, pipeline: Pipeline):
       await pipeline(Article(title=response.json()["title"]))
