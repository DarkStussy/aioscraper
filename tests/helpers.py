import asyncio
from typing import Callable

# Windows resolves loop timers at about 15.6ms, so a fixed sleep measures the clock, not the code.
_POLL_INTERVAL = 0.005
_SETTLE = 0.1


async def wait_for(condition: Callable[[], bool], *, timeout: float = 5.0):
    "Poll until the condition holds. Polling because the code under test has nothing to signal with."
    async with asyncio.timeout(timeout):
        while not condition():  # noqa: ASYNC110
            await asyncio.sleep(_POLL_INTERVAL)


async def wait_and_settle(condition: Callable[[], bool], *, timeout: float = 5.0, settle: float = _SETTLE):
    "Wait for the condition, then check it survives a pause. For upper bounds: N, and no more."
    await wait_for(condition, timeout=timeout)
    await asyncio.sleep(settle)
    assert condition()
