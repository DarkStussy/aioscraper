import asyncio
from contextlib import suppress
from unittest.mock import AsyncMock

import pytest

from aioscraper.config import Config, ExecutionConfig
from aioscraper.core.errors import RunResult
from aioscraper.core.runner import _run_scraper, _run_scraper_without_force_exit


def make_scraper_mock() -> AsyncMock:
    scraper = AsyncMock()
    scraper.entered = False
    scraper.exited = False
    scraper.started = False
    scraper.canceled = False
    scraper.canceled_by_timeout = False
    scraper._stop = asyncio.Event()
    scraper.result = RunResult()

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
            scraper.canceled = True
            scraper.canceled_by_timeout = True
        except asyncio.CancelledError:
            scraper.canceled = True
            raise

    scraper.__aenter__.side_effect = aenter
    scraper.__aexit__.side_effect = aexit
    scraper.wait.side_effect = wait
    scraper.stop = scraper._stop.set
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
    assert scraper.canceled is True


@pytest.mark.asyncio
async def test_shutdown_grants_grace_period_to_in_flight_work():
    """In-flight work that finishes inside shutdown_timeout must not be canceled."""
    scraper = make_scraper_mock()
    scraper.config = Config(execution=ExecutionConfig(timeout=None, shutdown_timeout=0.5))
    shutdown = asyncio.Event()

    async def trigger_shutdown():
        await asyncio.sleep(0.01)
        shutdown.set()
        # 150ms of work after the signal, well inside the 500ms grace period.
        await asyncio.sleep(0.15)
        scraper.stop()

    trigger = asyncio.create_task(trigger_shutdown())
    await _run_scraper_without_force_exit(scraper, shutdown)
    await trigger

    assert scraper.started is True
    assert scraper.exited is True
    assert scraper.canceled is False


@pytest.mark.asyncio
async def test_execution_timeout_cancels_scraper():
    scraper = make_scraper_mock()
    scraper.config = Config(execution=ExecutionConfig(timeout=0.02, shutdown_timeout=0.01))
    shutdown = asyncio.Event()

    await _run_scraper_without_force_exit(scraper, shutdown)

    assert scraper.canceled is True
    assert scraper.canceled_by_timeout is True


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

    assert scraper.canceled is True
