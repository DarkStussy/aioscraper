"""
AIOScraper inside a FastAPI service: one scraper for the life of the process.

The host framework's lifespan starts and stops it, routes hand it work through a queue, and both
the queue and the result store reach the callbacks through add_dependencies. Nothing here is
FastAPI-specific: any framework with a startup/shutdown hook wires up the same way.

Requires fastapi:

    $ pip install "aioscraper[aiohttp]" "fastapi[standard]"

Run it:

    $ fastapi dev web_service.py

Queue a repository, then read the result back:

    $ curl -X POST localhost:8000/repos/django/django
    $ curl localhost:8000/repos/django/django
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi import Request as WebRequest

from aioscraper import AIOScraper, Request, Response, ScheduleRequest, compiled

logger = logging.getLogger("web_service")

Stars = dict[str, int]


async def track_repos(schedule_request: ScheduleRequest, queue: asyncio.Queue[str]):
    "The entrypoint outlives every request: it takes repositories off the queue until shutdown."
    while True:
        repo = await queue.get()
        await schedule_request(
            Request(
                f"https://api.github.com/repos/{repo}",
                headers={"Accept": "application/vnd.github+json"},
                callback=store_stars,
                errback=on_failure,
                cb_kwargs={"repo": repo},
            ),
        )


@compiled
async def store_stars(response: Response, repo: str, stars: Stars):
    data = await response.json()
    stars[repo] = data["stargazers_count"]
    logger.info("%s: %s stars", repo, stars[repo])


@compiled
async def on_failure(exc: Exception, repo: str):
    logger.error("%s: %s", repo, exc, exc_info=exc)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    queue: asyncio.Queue[str] = asyncio.Queue()
    stars: Stars = {}

    scraper = AIOScraper(track_repos)
    scraper.add_dependencies(queue=queue, stars=stars)
    # start() returns immediately; the scraper runs alongside the server
    scraper.start()

    app.state.queue = queue
    app.state.stars = stars
    try:
        yield
    finally:
        await scraper.shutdown()


app = FastAPI(lifespan=lifespan)


@app.post("/repos/{owner}/{repo}", status_code=202)
async def queue_repo(request: WebRequest, owner: str, repo: str) -> dict[str, str]:
    "Hand the scraper work and return; the fetch happens outside the request."
    await request.app.state.queue.put(f"{owner}/{repo}")
    return {"status": "queued"}


@app.get("/repos/{owner}/{repo}")
async def read_repo(request: WebRequest, owner: str, repo: str) -> dict[str, int]:
    name = f"{owner}/{repo}"
    if (count := request.app.state.stars.get(name)) is None:
        raise HTTPException(status_code=404, detail="not fetched yet")

    return {"stars": count}
