#!/usr/bin/env python3
"""
Example scraper that fans out to GitHub's REST API to fetch repo metadata,
stores select fields via a pipeline, and prints a summary on shutdown.

Run with the CLI:

    $ aioscraper github_repos --concurrent-requests=2
"""

from dataclasses import dataclass
from enum import StrEnum, auto
from typing import Any

from aioscraper import AIOScraper
from aioscraper.types import Pipeline, Request, Response, SendRequest


scraper = AIOScraper()


class PipelineType(StrEnum):
    REPOS = auto()


@dataclass(slots=True)
class RepoItem:
    owner: str
    name: str
    data: dict[str, Any]


@scraper.pipeline(RepoItem)
class CollectPipeline:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    async def put_item(self, item: RepoItem) -> RepoItem:
        self.items.append(
            {
                "full_name": f"{item.owner}/{item.name}",
                "description": item.data.get("description"),
                "stars": item.data.get("stargazers_count"),
                "forks": item.data.get("forks_count"),
                "language": item.data.get("language"),
            }
        )
        return item

    async def close(self) -> None:
        print(f"Collected {len(self.items)} repos")
        for repo in self.items:
            print(
                f"{repo['full_name']}: ★{repo['stars']} forks:{repo['forks']} "
                f"lang:{repo['language']} - {repo['description']}"
            )


@scraper
async def fetch_repos(send_request: SendRequest) -> None:
    repos = [
        ("python", "cpython"),
        ("django", "django"),
        ("pallets", "flask"),
        ("tiangolo", "fastapi"),
        ("microsoft", "playwright-python"),
    ]

    async def parse_repo(response: Response, pipeline: Pipeline, owner: str, name: str) -> None:
        await pipeline(RepoItem(owner, name, data=response.json()))

    for owner, name in repos:
        await send_request(
            Request(
                url=f"https://api.github.com/repos/{owner}/{name}",
                callback=parse_repo,
                cb_kwargs={"owner": owner, "name": name},
                headers={
                    "User-Agent": "aioscraper-example/1.0",
                    "Accept": "application/vnd.github+json",
                },
            )
        )
