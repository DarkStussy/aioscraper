from decimal import Decimal
import json
from logging import getLevelNamesMapping
import os
from typing import Any, TypeVar, Callable


T = TypeVar("T")


class _NotSetType:
    def __repr__(self) -> str:
        return "NOTSET"


NOTSET = _NotSetType()


def _to_bool(v: str) -> bool:
    return v.lower() in {"true", "on", "ok", "y", "yes", "1"}


def _to_list(v: str) -> list[str]:
    return [item.strip() for item in v.split(",") if item.strip()]


def _to_tuple(v: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in v.split(",") if item.strip())


def _to_log_level(v: str) -> int:
    return getLevelNamesMapping()[v]


def parse(key: str, cast: Callable[[str], T], default: T | _NotSetType | None = NOTSET) -> T:
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


def parse_bool(key: str, default: bool | _NotSetType | None = NOTSET) -> bool:
    return parse(key, _to_bool, default)


def parse_int(key: str, default: int | _NotSetType | None = NOTSET) -> int:
    return parse(key, int, default)


def parse_float(key: str, default: float | _NotSetType | None = NOTSET) -> float:
    return parse(key, float, default)


def parse_decimal(key: str, default: Decimal | _NotSetType | None = NOTSET) -> Decimal:
    return parse(key, Decimal, default)


def parse_str(key: str, default: str | _NotSetType | None = NOTSET) -> str:
    return parse(key, str, default)


def parse_list(key: str, default: list[str] | _NotSetType | None = NOTSET) -> list[str]:
    return parse(key, _to_list, default)


def parse_tuple(key: str, default: tuple[str, ...] | _NotSetType | None = NOTSET) -> tuple[str, ...]:
    return parse(key, _to_tuple, default)


def parse_json(key: str, default: Any = NOTSET, load: Callable[[str], Any] | None = None) -> Any:
    return parse(key, load or json.loads, default)


def parse_log_level(key: str, default: int | None | _NotSetType = NOTSET) -> int:
    return parse(key, _to_log_level, default)
