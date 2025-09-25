from logging import getLogger
from typing import Any, Coroutine

logger = getLogger(__name__)


async def execute_coroutines(*coroutines: Coroutine[Any, Any, None]) -> None:
    for coroutine in coroutines:
        try:
            await coroutine
        except Exception as exc:
            logger.exception(exc)
