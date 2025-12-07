import asyncio
import logging
import signal
from contextlib import suppress
from functools import partial

from .scraper import AIOScraper

logger = logging.getLogger(__name__)


def _setup_signal_handlers(loop: asyncio.AbstractEventLoop, shutdown: asyncio.Event, force_exit: asyncio.Event):
    "Register SIGINT/SIGTERM handlers; repeated signal triggers force_exit."

    def _trigger(sig_name: str):
        if shutdown.is_set():
            if not force_exit.is_set():
                logger.error("Received second %s, ignore shutdown timeout", sig_name)
                force_exit.set()

            return

        logger.info("Received %s, starting shutdown", sig_name)
        shutdown.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        sig_name = signal.Signals(sig).name
        try:
            loop.add_signal_handler(sig, partial(_trigger, sig_name))
        except NotImplementedError:
            # Windows / limited envs: fallback to signal.signal
            try:
                signal.signal(sig, lambda *_: loop.call_soon_threadsafe(_trigger, sig_name))
            except (ValueError, RuntimeError):
                logger.debug("Signal handler for %s was not installed", sig_name)


async def _run_scraper_without_force_exit(scraper: AIOScraper, shutdown_event: asyncio.Event):
    "Run scraper with shutdown/timeout handling, ignoring force-exit logic."
    config = scraper.config
    assert config is not None

    execution_timeout = config.execution.timeout

    shutdown_task = asyncio.create_task(shutdown_event.wait())
    timeout_task = asyncio.create_task(asyncio.sleep(execution_timeout)) if execution_timeout is not None else None

    async with scraper:
        scraper_task = asyncio.create_task(scraper.start())
        wait_set = {scraper_task, shutdown_task}
        if timeout_task is not None:
            wait_set.add(timeout_task)

        done, _ = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)

        if scraper_task in done:
            shutdown_task.cancel()
            if timeout_task is not None:
                timeout_task.cancel()

            with suppress(asyncio.CancelledError):
                await shutdown_task
                if timeout_task is not None:
                    await timeout_task

            return await scraper_task

        if timeout_task is not None and timeout_task in done:
            logger.log(
                level=config.execution.log_level,
                msg=f"Execution timeout reached ({execution_timeout}s), cancelling tasks",
            )
            shutdown_task.cancel()
        else:
            logger.warning("Shutdown requested, cancelling tasks")
            if timeout_task is not None:
                timeout_task.cancel()

        scraper_task.cancel()
        try:
            await asyncio.wait_for(scraper_task, timeout=config.execution.shutdown_timeout)
        except asyncio.TimeoutError:
            logger.error("Shutdown timeout expired")
        except asyncio.CancelledError:
            pass
        finally:
            with suppress(asyncio.CancelledError):
                await shutdown_task
                if timeout_task is not None:
                    await timeout_task


async def _run_scraper(
    scraper: AIOScraper,
    shutdown_event: asyncio.Event | None = None,
    force_exit_event: asyncio.Event | None = None,
    install_signal_handlers: bool = True,
):
    "Main runner: wires signal handlers, listens for force-exit, delegates shutdown-aware execution."
    loop = asyncio.get_running_loop()
    shutdown = shutdown_event or asyncio.Event()
    force_exit = force_exit_event or asyncio.Event()
    if install_signal_handlers:
        _setup_signal_handlers(loop, shutdown, force_exit)

    force_exit_task = asyncio.create_task(force_exit.wait())
    scraper_task = asyncio.create_task(_run_scraper_without_force_exit(scraper, shutdown))

    done, _ = await asyncio.wait([force_exit_task, scraper_task], return_when=asyncio.FIRST_COMPLETED)

    if force_exit_task in done:
        scraper_task.cancel()
        with suppress(asyncio.CancelledError):
            await scraper_task

        return

    await scraper_task


async def run_scraper(scraper: AIOScraper):
    "Public entrypoint to run scraper with signal handling."
    await _run_scraper(scraper)
