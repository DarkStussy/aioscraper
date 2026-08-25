import asyncio
from typing import Any, Callable, Coroutine
from unittest.mock import AsyncMock

import pytest

from aioscraper.core import AIOScraper


def _scraper(run: Callable[[], Coroutine[Any, Any, None]] | None = None, **kwargs) -> AIOScraper:
    scraper = AIOScraper(**kwargs)
    scraper._run = run or AsyncMock()
    return scraper


async def test_start_twice_is_rejected():
    scraper = _scraper()
    scraper.start()

    with pytest.raises(RuntimeError, match="single-use"):
        scraper.start()

    await scraper.close()


async def test_start_after_close_is_rejected():
    scraper = _scraper()
    scraper.start()
    await scraper.close()

    with pytest.raises(RuntimeError, match="single-use"):
        scraper.start()


async def test_reentering_the_context_is_rejected():
    events = []

    async def lifespan(_: AIOScraper):
        events.append("startup")
        yield
        events.append("shutdown")

    scraper = _scraper(lifespan=lifespan)

    async with scraper:
        pass

    with pytest.raises(RuntimeError, match="single-use"):
        async with scraper:
            pass

    # the rejected run must not have set the lifespan up again
    assert events == ["startup", "shutdown"]


async def test_wait_before_start_is_rejected():
    with pytest.raises(RuntimeError, match="not started"):
        await _scraper().wait()


async def test_shutdown_before_start_is_rejected():
    with pytest.raises(RuntimeError, match="not started"):
        await _scraper().shutdown()


async def test_wait_after_close_returns_the_recorded_outcome():
    scraper = _scraper()

    async with scraper:
        await scraper.wait()

    result = await scraper.wait()

    assert result.ok is True
    assert result.timed_out is False


async def test_shutdown_after_close_returns_the_recorded_outcome():
    scraper = _scraper()

    async with scraper:
        await scraper.wait()

    assert (await scraper.shutdown()).ok is True


async def test_wait_after_close_before_start_is_rejected():
    scraper = _scraper()
    await scraper.close()

    with pytest.raises(RuntimeError, match="not started"):
        await scraper.wait()


async def test_close_is_idempotent():
    scraper = _scraper()
    scraper.start()

    await scraper.close()
    await scraper.close()


async def test_concurrent_entry_sets_the_lifespan_up_once():
    started = 0

    async def lifespan(_: AIOScraper):
        nonlocal started
        started += 1
        await asyncio.sleep(0)
        yield

    scraper = _scraper(lifespan=lifespan)
    entries = await asyncio.gather(
        scraper.__aenter__(),
        scraper.__aenter__(),
        return_exceptions=True,
    )

    assert started == 1
    assert [type(entry) for entry in entries].count(RuntimeError) == 1
    await scraper.close()


def test_start_without_a_running_loop_keeps_the_instance_startable():
    scraper = _scraper()

    with pytest.raises(RuntimeError, match="no running event loop"):
        scraper.start()

    async def run():
        async with scraper:
            assert (await scraper.wait()).ok is True

    asyncio.run(run())


async def test_concurrent_close_runs_teardown_once():
    teardown = 0

    async def run():
        nonlocal teardown
        try:
            await asyncio.Event().wait()
        finally:
            teardown += 1

    scraper = _scraper(run)
    scraper.start()
    await asyncio.sleep(0)

    await asyncio.gather(scraper.close(), scraper.close())

    assert teardown == 1


async def test_start_during_startup_is_rejected():
    runs = 0
    release_lifespan = asyncio.Event()

    async def run():
        nonlocal runs
        runs += 1
        await asyncio.Event().wait()

    async def lifespan(_: AIOScraper):
        await release_lifespan.wait()
        yield

    scraper = _scraper(run, lifespan=lifespan)
    entering = asyncio.create_task(scraper.__aenter__())
    await asyncio.sleep(0)

    with pytest.raises(RuntimeError, match="single-use"):
        scraper.start()

    release_lifespan.set()
    await asyncio.wait_for(entering, timeout=5.0)
    await asyncio.sleep(0)

    assert runs == 1
    await scraper.close()


async def test_close_waits_for_an_unfinished_startup():
    release_lifespan = asyncio.Event()
    canceled = asyncio.Event()

    async def run():
        try:
            await asyncio.Event().wait()
        finally:
            canceled.set()

    async def lifespan(_: AIOScraper):
        await release_lifespan.wait()
        yield

    scraper = _scraper(run, lifespan=lifespan)
    entering = asyncio.create_task(scraper.__aenter__())
    await asyncio.sleep(0)

    closing = asyncio.create_task(scraper.close())
    await asyncio.sleep(0)

    assert not closing.done()

    release_lifespan.set()
    await asyncio.wait_for(entering, timeout=5.0)
    await asyncio.wait_for(closing, timeout=5.0)

    assert canceled.is_set()
    with pytest.raises(RuntimeError, match="single-use"):
        scraper.start()


async def test_timeout_stays_on_the_result_after_close():
    async def run():
        await asyncio.Event().wait()

    scraper = _scraper(run)
    scraper.start()

    assert (await scraper.wait(timeout=0.01)).timed_out is True

    await scraper.close()
    result = await scraper.wait()

    assert result.timed_out is True
    assert result.ok is False


async def test_wait_in_flight_is_not_cancelled_by_close():
    teardown_started = asyncio.Event()
    release_teardown = asyncio.Event()

    async def run():
        try:
            await asyncio.Event().wait()
        finally:
            teardown_started.set()
            await release_teardown.wait()
            scraper._error_collector.record("close", RuntimeError("teardown failed"))

    scraper: AIOScraper = _scraper(run)
    scraper.start()
    await asyncio.sleep(0)

    waiting = asyncio.create_task(scraper.wait())
    await asyncio.sleep(0)

    closing = asyncio.create_task(scraper.close())
    await asyncio.wait_for(teardown_started.wait(), timeout=5.0)
    release_teardown.set()

    result = await asyncio.wait_for(waiting, timeout=5.0)
    await asyncio.wait_for(closing, timeout=5.0)

    assert result.error_counts == {"close": 1}
    assert result.ok is False


async def test_wait_with_zero_does_not_take_the_configured_timeout():
    """0 gives the run no time; the config timeout is None by default, so it would never return."""

    async def run():
        await asyncio.Event().wait()

    scraper = _scraper(run)
    scraper.start()
    await asyncio.sleep(0)

    result = await asyncio.wait_for(scraper.wait(timeout=0), timeout=5.0)

    assert result.timed_out is True
    await scraper.close()


async def test_wait_propagates_what_the_run_failed_with():
    async def run():
        raise ValueError("run failed")

    scraper = _scraper(run)
    scraper.start()

    with pytest.raises(ValueError, match="run failed"):
        await scraper.wait()

    # close() awaits the same task, so it surfaces the failure again
    with pytest.raises(ValueError, match="run failed"):
        await scraper.close()


async def test_wait_during_close_reports_errors_recorded_by_teardown():
    teardown_started = asyncio.Event()
    release_teardown = asyncio.Event()

    async def run():
        try:
            await asyncio.Event().wait()
        finally:
            teardown_started.set()
            await release_teardown.wait()
            scraper._error_collector.record("close", RuntimeError("teardown failed"))

    scraper: AIOScraper = _scraper(run)
    scraper.start()
    await asyncio.sleep(0)

    closing = asyncio.create_task(scraper.close())
    await asyncio.wait_for(teardown_started.wait(), timeout=5.0)

    waiting = asyncio.create_task(scraper.wait())
    await asyncio.sleep(0)
    release_teardown.set()

    result = await asyncio.wait_for(waiting, timeout=5.0)
    await asyncio.wait_for(closing, timeout=5.0)

    assert result.error_counts == {"close": 1}
    assert result.ok is False
