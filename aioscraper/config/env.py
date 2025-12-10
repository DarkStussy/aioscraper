import json
import os
from logging import getLevelNamesMapping
from typing import Any, Callable

from yarl import URL

from aioscraper.types.stub import NOTSET, NotSetType


def to_bool(v: str) -> bool:
    return v.lower() in {"true", "on", "ok", "y", "yes", "1"}


def to_list(v: str, cast: Callable[[str], Any]) -> list[Any]:
    return [cast(item.strip()) for item in v.split(",") if item.strip()]


def to_tuple(v: str, cast: Callable[[str], Any]) -> tuple[Any, ...]:
    return tuple(cast(item.strip()) for item in v.split(",") if item.strip())


def to_log_level(v: str) -> int:
    return getLevelNamesMapping()[v]


def parse(key: str, default: Any = NOTSET, *, cast: Callable[[str], Any] = str) -> Any:
    raw = os.getenv(key)
    if raw is None:
        if default is NOTSET:
            raise ValueError(f"Missing required environment variable: {key}")

        return default

    try:
        return cast(raw)
    except Exception as e:
        raise ValueError(f"Failed to cast environment variable {key}: {raw!r}") from e


def parse_list(
    key: str,
    default: list[str] | NotSetType | None = NOTSET,
    *,
    cast: Callable[[str], Any] = str,
) -> list[Any]:
    return parse(key, default, cast=lambda v: to_list(v, cast))


def parse_tuple(
    key: str,
    default: tuple[Any, ...] | NotSetType | None = NOTSET,
    *,
    cast: Callable[[str], Any] = str,
) -> tuple[Any, ...]:
    return parse(key, default, cast=lambda v: to_tuple(v, cast))


def parse_json(key: str, default: Any = NOTSET, *, load: Callable[[str], Any] | None = None) -> Any:
    return parse(key, default, cast=load or json.loads)


def parse_log_level(key: str, default: int | None | NotSetType = NOTSET) -> int:
    return parse(key, default, cast=to_log_level)


def parse_proxy(key: str, default: str | None = None) -> dict[str, str | None] | str | None:
    if value := parse(key, default):
        url_exc = None
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError) as e:
            url_exc = e

        json_exc = None
        try:
            return str(URL(value))
        except (ValueError, TypeError) as e:
            json_exc = e

        raise ExceptionGroup("Cannot parse proxy", [url_exc, json_exc])

    return None
