from decimal import Decimal
import json
from logging import getLevelNamesMapping
import os
from typing import Any, TypeVar, Callable

from yarl import URL

from .types import NotSetType


T = TypeVar("T")


NOTSET = NotSetType()


def to_bool(v: str) -> bool:
    return v.lower() in {"true", "on", "ok", "y", "yes", "1"}


def to_list(v: str) -> list[str]:
    return [item.strip() for item in v.split(",") if item.strip()]


def to_tuple(v: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in v.split(",") if item.strip())


def to_log_level(v: str) -> int:
    return getLevelNamesMapping()[v]


def parse(key: str, cast: Callable[[str], T], default: T | NotSetType | None = NOTSET) -> T:
    raw = os.getenv(key)
    if raw is None:
        if default is NOTSET:
            raise ValueError(f"Missing required environment variable: {key}")

        return default  # type: ignore

    if cast is None:
        return raw

    try:
        return cast(raw)
    except Exception as e:
        raise ValueError(f"Failed to cast environment variable {key}: {raw!r}") from e


def parse_bool(key: str, default: bool | NotSetType | None = NOTSET) -> bool:
    return parse(key, to_bool, default)


def parse_int(key: str, default: int | NotSetType | None = NOTSET) -> int:
    return parse(key, int, default)


def parse_float(key: str, default: float | NotSetType | None = NOTSET) -> float:
    return parse(key, float, default)


def parse_decimal(key: str, default: Decimal | NotSetType | None = NOTSET) -> Decimal:
    return parse(key, Decimal, default)


def parse_str(key: str, default: str | NotSetType | None = NOTSET) -> str:
    return parse(key, str, default)


def parse_list(key: str, default: list[str] | NotSetType | None = NOTSET) -> list[str]:
    return parse(key, to_list, default)


def parse_tuple(key: str, default: tuple[str, ...] | NotSetType | None = NOTSET) -> tuple[str, ...]:
    return parse(key, to_tuple, default)


def parse_json(key: str, default: Any = NOTSET, load: Callable[[str], Any] | None = None) -> Any:
    return parse(key, load or json.loads, default)


def parse_log_level(key: str, default: int | None | NotSetType = NOTSET) -> int:
    return parse(key, to_log_level, default)


def parse_proxy(key: str, default: str | None = None) -> dict[str, str | None] | str | None:
    value = parse_str(key, default)
    if not value:
        return None

    url_exc = None
    try:
        proxies = json.loads(value)
        return {"http://": proxies.get("http"), "https://": proxies.get("https")}
    except Exception as e:
        url_exc = e

    json_exc = None
    try:
        return str(URL(value))
    except Exception as e:
        json_exc = e

    raise ExceptionGroup("Cannot parse proxy", [url_exc, json_exc])
