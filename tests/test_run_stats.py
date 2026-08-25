from dataclasses import dataclass

import pytest

from aioscraper.config import Config, RequestRetryConfig, SessionConfig
from aioscraper.core import AIOScraper
from aioscraper.core.errors import RunResult
from aioscraper.types import Request, Response, ScheduleRequest
from tests.mocks import MockAIOScraper, MockResponse


@dataclass
class Item:
    value: str


class CollectPipeline:
    def __init__(self):
        self.items: list[Item] = []

    async def put_item(self, item: Item) -> Item:
        self.items.append(item)
        return item

    async def close(self): ...


async def test_a_successful_run_counts_its_requests_and_items(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add("https://api.test.com/one", handler=lambda _: {"value": "one"})
    mock_aioscraper.server.add("https://api.test.com/two", handler=lambda _: {"value": "two"})
    mock_aioscraper.pipeline.add(Item, CollectPipeline())

    @mock_aioscraper
    async def scraper(schedule_request: ScheduleRequest):
        for path in ("one", "two"):
            await schedule_request(Request(url=f"https://api.test.com/{path}", callback=callback))

    async def callback(response: Response, pipeline):
        await pipeline(Item(value=(await response.json())["value"]))

    async with mock_aioscraper:
        result = await mock_aioscraper.wait()

    assert result.requests_started == 2
    assert result.requests_succeeded == 2
    assert result.requests_failed == 0
    assert result.requests_retried == 0
    assert result.items_processed == 2
    assert result.ok is True
    assert result.all_requests_succeeded is True


async def test_a_failing_request_counts_as_failed(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add(
        "https://api.test.com/broken",
        handler=lambda _: MockResponse(status=500, text="boom"),
    )

    @mock_aioscraper
    async def scraper(schedule_request: ScheduleRequest):
        await schedule_request(Request(url="https://api.test.com/broken"))

    async with mock_aioscraper:
        result = await mock_aioscraper.wait()

    assert result.requests_started == 1
    assert result.requests_succeeded == 0
    assert result.requests_failed == 1
    assert result.error_counts == {"request": 1}


async def test_a_handled_failure_counts_as_failed_but_is_not_an_error(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add(
        "https://api.test.com/broken",
        handler=lambda _: MockResponse(status=500, text="boom"),
    )
    handled: list[Exception] = []

    @mock_aioscraper
    async def scraper(schedule_request: ScheduleRequest):
        await schedule_request(Request(url="https://api.test.com/broken", errback=errback))

    async def errback(exc: Exception):
        handled.append(exc)

    async with mock_aioscraper:
        result = await mock_aioscraper.wait()

    assert len(handled) == 1
    assert result.requests_failed == 1
    assert result.error_counts == {}
    assert result.ok is True
    # ok is about what nobody handled; this is about the requests themselves
    assert result.all_requests_succeeded is False


async def test_a_retried_request_starts_once_per_attempt(mock_aioscraper: MockAIOScraper):
    mock_aioscraper.server.add(
        "https://api.test.com/flaky",
        handler=lambda _: MockResponse(status=503, text="unavailable"),
    )
    mock_aioscraper.server.add("https://api.test.com/flaky", handler=lambda _: {"value": "ok"})
    mock_aioscraper.config = Config(
        session=SessionConfig(retry=RequestRetryConfig(enabled=True, attempts=2, base_delay=0.001)),
    )

    @mock_aioscraper
    async def scraper(schedule_request: ScheduleRequest):
        await schedule_request(Request(url="https://api.test.com/flaky", callback=callback))

    async def callback(response: Response): ...

    async with mock_aioscraper:
        result = await mock_aioscraper.wait()

    assert result.requests_started == 2
    assert result.requests_succeeded == 1
    assert result.requests_failed == 0
    assert result.requests_retried == 1
    # the 503 ended an attempt, not the request: the retry got the data
    assert result.all_requests_succeeded is True


def test_the_result_is_built_by_keyword():
    """Field order is not API: a new counter must never shift onto an existing name."""
    with pytest.raises(TypeError):
        RunResult((), {})  # type: ignore[reportCallIssue]


@pytest.mark.parametrize(
    "attribute",
    ["requests_started", "requests_succeeded", "requests_failed", "requests_retried", "items_processed"],
)
def test_a_scraper_that_never_ran_counts_nothing(attribute: str):
    assert getattr(AIOScraper().result, attribute) == 0
