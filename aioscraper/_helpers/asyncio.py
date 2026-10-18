import asyncio
from logging import getLogger
from typing import Any, Callable, Coroutine

logger = getLogger(__name__)

ErrorHandler = Callable[[BaseException], None]


async def execute_coroutines(*coroutines: Coroutine[Any, Any, None], on_error: ErrorHandler | None = None):
    "Run coroutines in order, keeping going when one fails or the caller is canceled."
    canceled: asyncio.CancelledError | None = None
    for coroutine in coroutines:
        try:
            await execute_coroutine(coroutine, on_error=on_error)
        except asyncio.CancelledError as exc:
            canceled = exc

    if canceled is not None:
        raise canceled


async def execute_coroutine(coroutine: Coroutine[Any, Any, None], *, on_error: ErrorHandler | None = None):
    "Run a coroutine, logging any failure instead of propagating it."
    try:
        await coroutine
    except Exception as exc:
        logger.exception("Error occurred while executing coroutine %s", coroutine.__name__)
        if on_error is not None:
            on_error(exc)
