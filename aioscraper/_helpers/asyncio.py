from logging import Logger
from typing import Any, Coroutine


async def execute_coroutines(logger: Logger, *coroutines: Coroutine[Any, Any, None]) -> None:
    for coroutine in coroutines:
        try:
            await coroutine
        except Exception as exc:
            logger.exception(exc)
