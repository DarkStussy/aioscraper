import inspect
from functools import wraps
from typing import Any, Callable


def get_func_kwargs(func: Callable[..., Any], /, **kwargs: Any) -> dict[str, Any]:
    return {param: kwargs[param] for param in inspect.signature(func).parameters if param in kwargs}


def compiled(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Take the parameter names of a callback once, at import time, instead of on every call.

    Without it every call inspects the signature to decide which dependencies to pass. Use it on
    callbacks and errbacks that run often; the injection they get is the same either way.
    """
    params = set(inspect.signature(func).parameters)

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        filtered = {k: v for k, v in kwargs.items() if k in params}
        return await func(*args, **filtered)

    wrapper.__compiled__ = True  # type: ignore[reportAttributeAccessIssue]
    return wrapper
