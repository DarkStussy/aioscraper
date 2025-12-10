from logging import getLogger
from typing import Any, Coroutine

logger = getLogger(__name__)


async def execute_coroutines(*coroutines: Coroutine[Any, Any, None]):
    for coroutine in coroutines:
        try:
            await coroutine
        except Exception:
            logger.exception("Error occurred while executing coroutine %s", coroutine.__name__)


async def execute_coroutine(coroutine: Coroutine[Any, Any, None]):
    try:
        await coroutine
    except Exception:
        logger.exception("Error occurred while executing coroutine %s", coroutine.__name__)
