from unittest.mock import AsyncMock

import pytest

from aioscraper.core import AIOScraper


async def test_lifespan_startup_shutdown():
    startup_mock = AsyncMock()
    shutdown_mock = AsyncMock()

    async def lifespan(scraper: AIOScraper):
        await startup_mock()
        yield
        await shutdown_mock()

    scraper = AIOScraper(lifespan=lifespan)
    scraper._run = AsyncMock()

    async with scraper:
        startup_mock.assert_called_once()
        shutdown_mock.assert_not_called()

    shutdown_mock.assert_called_once()


async def test_lifespan_decorator():
    events = []

    scraper = AIOScraper()
    scraper._run = AsyncMock()

    @scraper.lifespan
    async def lifespan(instance: AIOScraper):
        assert instance is scraper
        events.append("startup")
        yield
        events.append("shutdown")

    async with scraper:
        assert events == ["startup"]

    assert events == ["startup", "shutdown"]


async def test_lifespan_error_in_startup():
    async def simple_lifespan(scraper: AIOScraper):
        raise ValueError("Startup error")
        yield

    scraper = AIOScraper(lifespan=simple_lifespan)
    scraper._run = AsyncMock()

    with pytest.raises(ValueError, match="Startup error"):
        async with scraper:
            pass


async def test_lifespan_error_in_shutdown():
    async def simple_lifespan(scraper: AIOScraper):
        yield
        raise ValueError("Shutdown error")

    scraper = AIOScraper(lifespan=simple_lifespan)
    scraper._run = AsyncMock()

    with pytest.raises(ValueError, match="Shutdown error"):
        async with scraper:
            pass


async def test_multiple_lifespans_override():
    # Only the last registered lifespan should be active
    events = []

    async def lifespan1(scraper: AIOScraper):
        events.append("1_start")
        yield
        events.append("1_stop")

    async def lifespan2(scraper: AIOScraper):
        events.append("2_start")
        yield
        events.append("2_stop")

    scraper = AIOScraper(lifespan=lifespan1)
    # This manually overwrites the internal handler via the decorator method
    scraper.lifespan(lifespan2)
    scraper._run = AsyncMock()

    async with scraper:
        assert events == ["2_start"]

    assert events == ["2_start", "2_stop"]


async def test_lifespan_execution_order():
    events = []

    async def lifespan(scraper: AIOScraper):
        events.append("startup")
        yield
        events.append("shutdown")

    scraper = AIOScraper(lifespan=lifespan)

    # Mock the start method to verify it runs after startup
    original_start = scraper.start
    scraper.start = lambda: events.append("start") or original_start()
    scraper._run = AsyncMock()

    async with scraper:
        assert events == ["startup", "start"]

    assert events == ["startup", "start", "shutdown"]
