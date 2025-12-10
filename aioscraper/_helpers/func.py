import inspect
from typing import Any, Callable


def get_func_kwargs(func: Callable[..., Any], **kwargs: Any) -> dict[str, Any]:
    return {param: kwargs[param] for param in inspect.signature(func).parameters if param in kwargs}
