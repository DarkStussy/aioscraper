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
