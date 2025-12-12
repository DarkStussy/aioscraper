import inspect
from functools import wraps
from typing import Any, Callable


def get_func_kwargs(func: Callable[..., Any], **kwargs: Any) -> dict[str, Any]:
    return {param: kwargs[param] for param in inspect.signature(func).parameters if param in kwargs}


def compiled(func: Callable[..., Any]) -> Callable[..., Any]:
    """
    Decorator that optimizes dependency injection by caching function parameters.

    Replaces runtime inspection with compile-time parameter extraction.
    """
    params = set(inspect.signature(func).parameters)

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        filtered = {k: v for k, v in kwargs.items() if k in params}
        return await func(*args, **filtered)

    wrapper.__compiled__ = True  # type: ignore[reportAttributeAccessIssue]
    return wrapper
