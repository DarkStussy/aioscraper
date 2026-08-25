import importlib
import ssl as ssl_module

_BOOLEAN_WORDS = frozenset({"true", "false"})


def parse_exception(path: str) -> type[BaseException]:
    """Import an exception class from a fully qualified path.

    Args:
        path (str): Dotted path, such as ``"aioscraper.exceptions.TransportTimeout"``.

    Returns:
        type[BaseException]: The imported class.

    Raises:
        ValueError: The path carries no module, names nothing importable, or names something that
            is not an exception type. What the import raised is chained onto it.
    """
    module_name, _, attr = path.rpartition(".")
    if not module_name:
        raise ValueError(f"Expected fully qualified exception path, got {path!r}")

    try:
        exc = getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError) as error:
        raise ValueError(f"Cannot import {path!r}: {error}") from error

    if isinstance(exc, type) and issubclass(exc, BaseException):
        return exc

    raise ValueError(f"{path!r} is not an exception type")


def parse_ssl(value: str) -> ssl_module.SSLContext | bool:
    """Read :attr:`SessionConfig.ssl <aioscraper.config.models.SessionConfig>` out of a string.

    Args:
        value (str): ``"true"`` or ``"false"``, or a path to a CA bundle to verify against.

    Returns:
        ssl.SSLContext | bool: The bool the word names, or a default context loaded with that bundle.

    Raises:
        ValueError: Anything else is read as a path, and no bundle could be loaded from it. What
            the load raised - a missing file, an unreadable one - is chained onto it.
    """
    if value.lower() in _BOOLEAN_WORDS:
        return value.lower() == "true"

    context = ssl_module.create_default_context()
    try:
        # SSLError is an OSError, so this covers a missing file and a malformed one alike
        context.load_verify_locations(value)
    except OSError as error:
        raise ValueError(f"Cannot load a CA bundle from {value!r}: {error}") from error

    return context
