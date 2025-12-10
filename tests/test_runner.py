import asyncio
from contextlib import suppress
from unittest.mock import AsyncMock

import pytest

from aioscraper.config import Config, ExecutionConfig
from aioscraper.core.runner import _run_scraper, _run_scraper_without_force_exit


def make_scraper_mock() -> AsyncMock:
    scraper = AsyncMock()
    scraper.entered = False
    scraper.exited = False
    scraper.started = False
    scraper.cancelled = False
    scraper.cancelled_by_timeout = False
    scraper._stop = asyncio.Event()

    async def aenter():
        scraper.entered = True
        return scraper

    async def aexit(exc_type, exc_val, exc_tb):
        scraper.exited = True

    async def wait():
        scraper.started = True
        try:
            await asyncio.wait_for(scraper._stop.wait(), scraper.config.execution.timeout)
        except TimeoutError:
            scraper.cancelled = True
            scraper.cancelled_by_timeout = True
        except asyncio.CancelledError:
            scraper.cancelled = True
            raise

    scraper.__aenter__.side_effect = aenter
    scraper.__aexit__.side_effect = aexit
    scraper.wait.side_effect = wait
    scraper.stop = lambda: scraper._stop.set()
    return scraper


@pytest.mark.asyncio
async def test_shutdown_event_cancels_scraper():
    scraper = make_scraper_mock()
    scraper.config = Config(execution=ExecutionConfig(timeout=None, shutdown_timeout=0.05))
    shutdown = asyncio.Event()

    async def trigger_shutdown():
        await asyncio.sleep(0.01)
        shutdown.set()

    trigger = asyncio.create_task(trigger_shutdown())
    await _run_scraper_without_force_exit(scraper, shutdown)
    trigger.cancel()
    with suppress(asyncio.CancelledError):
        await trigger

    assert scraper.entered is True
    assert scraper.exited is True
    assert scraper.started is True
    assert scraper.cancelled is True


@pytest.mark.asyncio
async def test_execution_timeout_cancels_scraper():
    scraper = make_scraper_mock()
    scraper.config = Config(execution=ExecutionConfig(timeout=0.02, shutdown_timeout=0.01))
    shutdown = asyncio.Event()

    await _run_scraper_without_force_exit(scraper, shutdown)

    assert scraper.cancelled is True
    assert scraper.cancelled_by_timeout is True


@pytest.mark.asyncio
async def test_force_exit_path():
    scraper = make_scraper_mock()
    scraper.config = Config(execution=ExecutionConfig(timeout=None, shutdown_timeout=0.05))
    shutdown = asyncio.Event()
    force_exit = asyncio.Event()

    async def trigger_force_exit():
        shutdown.set()
        await asyncio.sleep(0.01)
        force_exit.set()

    trigger = asyncio.create_task(trigger_force_exit())
    await _run_scraper(
        scraper,
        shutdown_event=shutdown,
        force_exit_event=force_exit,
        install_signal_handlers=False,
    )
    trigger.cancel()
    with suppress(asyncio.CancelledError):
        await trigger

    assert scraper.cancelled is True
