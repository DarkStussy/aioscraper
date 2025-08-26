import inspect
from logging import Logger
from typing import Callable, Any, Coroutine


def get_func_kwargs(func: Callable, kwargs: dict[str, Any]) -> dict[str, Any]:
    return {param: kwargs[param] for param in inspect.signature(func).parameters.keys() if param in kwargs}


def get_cb_kwargs(callback: Callable, srv_kwargs: dict[str, Any], cb_kwargs: dict[str, Any] | None) -> dict[str, Any]:
    if cb_kwargs is None and not srv_kwargs:
        return {}

    if cb_kwargs is None:
        cb_kwargs = {}

    return get_func_kwargs(callback, cb_kwargs | srv_kwargs)


async def execute_coroutines(logger: Logger, *coroutines: Coroutine) -> Any:
    for coroutine in coroutines:
        try:
            await coroutine
        except Exception as exc:
            logger.exception(exc)
