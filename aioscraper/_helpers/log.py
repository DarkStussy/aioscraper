import inspect
from typing import Any


def get_log_name(obj: Any) -> str:
    return obj.__name__ if inspect.isclass(obj) else type(obj).__name__
