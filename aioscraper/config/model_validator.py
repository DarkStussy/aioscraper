from contextlib import contextmanager
from dataclasses import fields, field as dc_field, MISSING
from enum import Enum
from types import GenericAlias
from typing import Any, Callable, Iterator, Type, TypeVar, cast, get_origin, get_args, get_type_hints

from .field_validators import Validator
from ..exceptions import ConfigValidationError


_T = TypeVar("_T")


@contextmanager
def _format_error(cls_name: str, field: str) -> Iterator[None]:
    try:
        yield
    except Exception as exc:
        raise ConfigValidationError(f"{cls_name}.{field}: {exc}") from exc


def _try_cast(value: Any, target_type: Type[_T]) -> _T:
    if target_type is bool:
        v = value.lower().strip()
        if v in ("true", "on", "ok", "y", "yes", "1"):
            return cast(_T, True)
        if v in ("false", "0", "no"):
            return cast(_T, False)

        raise ValueError(f"Cannot cast '{value}' to bool")

    if issubclass(target_type, Enum):
        try:
            return target_type(value)
        except ValueError as e:
            raise ValueError(f"Cannot cast '{value}' to {target_type}") from e

    ctor = cast(Callable[[Any], _T], target_type)
    try:
        return ctor(value)
    except Exception as e:
        raise ValueError(f"Cannot cast '{value}' to {target_type}") from e


def _validate_and_cast(value: Any, annotation: type) -> Any:
    origin = get_origin(annotation)
    args = get_args(annotation)

    if origin is None:
        if isinstance(value, annotation):
            return value

        if isinstance(value, str) or (isinstance(value, int) and issubclass(annotation, float)):
            return _try_cast(value, annotation)

        raise TypeError(f"Expected {annotation}, got {type(value)}")

    if origin is str or origin is dict:
        return value

    if origin is None:
        return value

    if origin in (list, dict, tuple):
        return value

    if origin is not None:  # Union
        for t in args:
            if t is type(None) and value is None:
                return None

            if isinstance(t, GenericAlias):
                t: type = t.__origin__  # type: ignore

            if isinstance(value, t):
                return value

            if isinstance(value, str):
                try:
                    return _try_cast(value, t)
                except Exception:
                    pass

        raise TypeError(f"Value '{value}' does not match any type in {annotation}")

    return value


def validate(cls: type[_T]) -> type[_T]:
    orig_post_init = getattr(cls, "__post_init__", None)
    hints = get_type_hints(cls)

    def __post_init__(self, *args, **kwargs):
        for f in fields(self):
            if f.metadata.get("skip_validation"):
                continue

            annotation = hints.get(f.name, f.type)
            if isinstance(annotation, str):
                continue

            value = getattr(self, f.name)
            with _format_error(cls.__name__, f.name):
                new_value = _validate_and_cast(value, annotation)

            if validator := f.metadata.get("validator"):
                with _format_error(cls.__name__, f.name):
                    new_value = validator(f.name, new_value)

            if new_value is not value:
                object.__setattr__(self, f.name, new_value)

        if orig_post_init:
            orig_post_init(self, *args, **kwargs)

    setattr(cls, "__post_init__", __post_init__)
    return cls


def field(
    *,
    default: Any = MISSING,
    default_factory: Any = MISSING,
    init: bool = True,
    repr: bool = True,
    hash: Any = None,
    compare: bool = True,
    metadata: dict[Any, Any] | None = None,
    kw_only: bool = False,
    validator: Validator | None = None,
    skip_validation: bool = False,
) -> Any:
    """Wraps a dataclass field with optional validation."""
    metadata = metadata or {}
    metadata["validator"] = validator
    metadata["skip_validation"] = skip_validation
    return dc_field(
        default=default,
        default_factory=default_factory,
        init=init,
        repr=repr,
        hash=hash,
        compare=compare,
        metadata=metadata,
        kw_only=kw_only,
    )
