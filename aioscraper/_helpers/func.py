import inspect
from typing import Callable, Any


def get_func_kwargs(func: Callable[..., Any], kwargs: dict[str, Any]) -> dict[str, Any]:
    return {param: kwargs[param] for param in inspect.signature(func).parameters.keys() if param in kwargs}


def get_cb_kwargs(cb: Callable[..., Any], kwargs: dict[str, Any] | None, deps: dict[str, Any]) -> dict[str, Any]:
    if kwargs is None and not deps:
        return {}

    if kwargs is None:
        kwargs = {}

    return get_func_kwargs(cb, kwargs | deps)
