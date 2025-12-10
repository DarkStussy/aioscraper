import importlib


def import_exception(path: str) -> type[BaseException]:
    module_name, _, attr = path.rpartition(".")
    if not module_name:
        raise ValueError(f"Expected fully qualified exception path, got {path!r}")

    module = importlib.import_module(module_name)
    exc = getattr(module, attr)
    if not isinstance(exc, type) or not issubclass(exc, BaseException):
        raise TypeError(f"{path!r} is not an exception type")

    return exc
