import inspect
from typing import Callable, Any


def get_func_kwargs(func: Callable, kwargs: dict[str, Any]) -> dict[str, Any]:
    return {param: kwargs[param] for param in inspect.signature(func).parameters.keys() if param in kwargs}


def get_cb_kwargs(
    callback: Callable,
    srv_kwargs: dict[str, Any] | None,
    cb_kwargs: dict[str, Any] | None,
) -> dict[str, Any]:
    if cb_kwargs is None and srv_kwargs is None:
        return {}

    if cb_kwargs is None:
        cb_kwargs = {}
    if srv_kwargs is None:
        srv_kwargs = {}

    return get_func_kwargs(callback, cb_kwargs | srv_kwargs)
