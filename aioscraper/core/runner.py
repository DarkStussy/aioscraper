import asyncio
import logging
import signal
from contextlib import suppress
from dataclasses import replace
from functools import partial
from types import FrameType
from typing import Any, Callable

from .errors import RunResult
from .scraper import AIOScraper

logger = logging.getLogger(__name__)

_SignalHandler = Callable[[int, FrameType | None], Any] | int | signal.Handlers | None


class _SignalDispatch:
    "SIGINT/SIGTERM handlers shared by the runs on one loop: the first installs, the last restores."

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._triggers: list[Callable[[str], None]] = []
        self._undo: list[Callable[[], None]] = []

    def add(self, trigger: Callable[[str], None]):
        if not self._triggers:
            self._install()

        self._triggers.append(trigger)

    def remove(self, trigger: Callable[[str], None]) -> bool:
        "Drop a run's trigger; ``True`` once the last one is gone and the handlers are restored."
        self._triggers.remove(trigger)
        if self._triggers:
            return False

        for step in self._undo:
            step()

        self._undo.clear()
        return True

    def _dispatch(self, sig_name: str):
        for trigger in tuple(self._triggers):
            trigger(sig_name)

    def _install(self):
        for sig in (signal.SIGINT, signal.SIGTERM):
            sig_name = signal.Signals(sig).name
            previous = signal.getsignal(sig)
            try:
                self._loop.add_signal_handler(sig, self._dispatch, sig_name)
                self._undo.append(partial(_remove_loop_handler, self._loop, sig, previous))
            except NotImplementedError:
                # Windows / limited envs: fallback to signal.signal
                try:
                    signal.signal(sig, lambda *_, s=sig_name: self._loop.call_soon_threadsafe(self._dispatch, s))
                    self._undo.append(partial(_restore_handler, sig, previous))
                except (ValueError, RuntimeError):
                    logger.debug("Signal handler for %s was not installed", sig_name)


_dispatches: dict[asyncio.AbstractEventLoop, _SignalDispatch] = {}


def _setup_signal_handlers(
    loop: asyncio.AbstractEventLoop,
    shutdown: asyncio.Event,
    force_exit: asyncio.Event,
) -> Callable[[], None]:
    "Register SIGINT/SIGTERM handlers; repeated signal triggers force_exit. Returns the undo."

    def _trigger(sig_name: str):
        if shutdown.is_set():
            if not force_exit.is_set():
                logger.warning("Received second %s, ignore shutdown timeout", sig_name)
                force_exit.set()

            return

        logger.info("Received %s, starting shutdown", sig_name)
        shutdown.set()

    dispatch = _dispatches.setdefault(loop, _SignalDispatch(loop))
    dispatch.add(_trigger)

    def restore():
        if dispatch.remove(_trigger):
            _dispatches.pop(loop, None)

    return restore


def _remove_loop_handler(loop: asyncio.AbstractEventLoop, sig: signal.Signals, previous: _SignalHandler):
    # removal installs the default handler, not the one that was there before
    loop.remove_signal_handler(sig)
    _restore_handler(sig, previous)


def _restore_handler(sig: signal.Signals, previous: _SignalHandler):
    # None: the previous handler was not installed from Python and cannot be put back
    if previous is not None:
        signal.signal(sig, previous)


async def _cancel(task: asyncio.Task[Any]):
    "Cancel a task and wait for it to settle."
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task


async def _run_scraper_without_force_exit(scraper: AIOScraper, shutdown_event: asyncio.Event) -> RunResult | None:
    "Run to completion, or until a signal, which buys in-flight work ``shutdown_timeout`` to finish."
    shutdown_task = asyncio.create_task(shutdown_event.wait())

    async with scraper:
        scraper_task = asyncio.create_task(scraper.wait())
        wait_set = {scraper_task, shutdown_task}

        done, _ = await asyncio.wait(wait_set, return_when=asyncio.FIRST_COMPLETED)

        if scraper_task in done:
            await _cancel(shutdown_task)
            return await scraper_task

        shutdown_timeout = scraper.config.execution.shutdown_timeout
        logger.warning("Shutdown requested, waiting for scraper to finish (timeout=%0.10gs)", shutdown_timeout)

        # wait_for cancels the shield wrapper on timeout, not scraper_task itself,
        # so the cancellation below happens only after the grace period.
        try:
            return await asyncio.wait_for(asyncio.shield(scraper_task), timeout=shutdown_timeout)
        except asyncio.TimeoutError:
            logger.warning("Shutdown timeout expired, canceling tasks")
            await _cancel(scraper_task)
        except asyncio.CancelledError:
            await _cancel(scraper_task)
            raise
        finally:
            with suppress(asyncio.CancelledError):
                await shutdown_task


async def _run_scraper(
    scraper: AIOScraper,
    *,
    shutdown_event: asyncio.Event | None = None,
    force_exit_event: asyncio.Event | None = None,
    install_signal_handlers: bool = True,
) -> RunResult:
    "Main runner: installs the signal handlers for the run's duration."
    loop = asyncio.get_running_loop()
    shutdown = shutdown_event or asyncio.Event()
    force_exit = force_exit_event or asyncio.Event()
    restore_signal_handlers = _setup_signal_handlers(loop, shutdown, force_exit) if install_signal_handlers else None
    try:
        return await _run_with_force_exit(scraper, shutdown, force_exit)
    finally:
        if restore_signal_handlers is not None:
            restore_signal_handlers()


async def _run_with_force_exit(scraper: AIOScraper, shutdown: asyncio.Event, force_exit: asyncio.Event) -> RunResult:
    "Run until done, or cancel the run on force_exit."
    force_exit_task = asyncio.create_task(force_exit.wait())
    scraper_task = asyncio.create_task(_run_scraper_without_force_exit(scraper, shutdown))

    done, _ = await asyncio.wait([force_exit_task, scraper_task], return_when=asyncio.FIRST_COMPLETED)

    if force_exit_task in done:
        await _cancel(scraper_task)
        return replace(scraper.result, interrupted=True)

    await _cancel(force_exit_task)
    await scraper_task
    # Read after the task rather than taken from what it returned: teardown runs once wait() is
    # done and records errors of its own.
    #
    # The handlers turn SIGINT/SIGTERM into an event, so KeyboardInterrupt never reaches the
    # caller: without this flag a signaled run is indistinguishable from a clean one.
    return replace(scraper.result, interrupted=shutdown.is_set())


async def run_scraper(scraper: AIOScraper, *, install_signal_handlers: bool = True) -> RunResult:
    """Run the scraper with signal handling.

    SIGINT/SIGTERM start a graceful shutdown; a second one cancels the run. Overlapping runs share
    the handlers and each gets the signal. The last run to end puts the previous handlers back,
    except one registered with ``loop.add_signal_handler``, which asyncio does not expose.

    Args:
        scraper (AIOScraper): The scraper to run; its ``config`` must already be set.
        install_signal_handlers (bool): ``False`` leaves signals to the application embedding the run.

    Returns:
        RunResult: Unhandled errors, and whether a signal or the timeout stopped the run.
    """
    return await _run_scraper(scraper, install_signal_handlers=install_signal_handlers)
