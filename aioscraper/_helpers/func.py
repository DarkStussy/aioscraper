import inspect
from typing import Callable, Any


def get_func_kwargs(func: Callable[..., Any], **kwargs: Any) -> dict[str, Any]:
    return {param: kwargs[param] for param in inspect.signature(func).parameters.keys() if param in kwargs}
