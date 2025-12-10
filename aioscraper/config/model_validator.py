from contextlib import contextmanager
from dataclasses import MISSING, fields
from dataclasses import field as dc_field
from enum import Enum
from types import GenericAlias
from typing import Any, Callable, Iterator, TypeVar, cast, get_args, get_origin, get_type_hints

from aioscraper.exceptions import ConfigValidationError

from .field_validators import Validator

_T = TypeVar("_T")


@contextmanager
def _format_error(cls_name: str, field: str) -> Iterator[None]:
    try:
        yield
    except Exception as exc:
        raise ConfigValidationError(f"{cls_name}.{field}: {exc}") from exc


def _try_cast(value: Any, target_type: type[_T]) -> _T:
    if target_type is bool:
        v = value.lower().strip()
        if v in ("true", "on", "ok", "y", "yes", "1"):
            return cast(_T, val=True)
        if v in ("false", "0", "no"):
            return cast(_T, val=False)

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

    if origin in (str, dict, list, dict, tuple):
        return value
    elif origin is not None:  # Union
        if bool in args and isinstance(value, str):
            try:
                return _try_cast(value, bool)
            except ValueError:
                pass

        for t in args:
            if t is type(None) and value is None:
                return None

            if isinstance(t, GenericAlias):
                if isinstance(value, t.__origin__):  # type: ignore[reportArgumentType]
                    return value
            elif isinstance(value, t):
                return value
            elif isinstance(value, str):
                return _try_cast(value, t)

        raise TypeError(f"Value '{value}' does not match any type in {annotation}")

    return value


def validate(cls: type[_T]) -> type[_T]:
    orig_post_init = getattr(cls, "__post_init__", None)
    hints = get_type_hints(cls)

    def post_init(self, *args, **kwargs):
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

    cls.__post_init__ = post_init  # type: ignore[reportAttributeAccessIssue]
    return cls


def field(
    *,
    default: Any = MISSING,
    default_factory: Any = MISSING,
    init_: bool = True,
    repr_: bool = True,
    hash_: Any = None,
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
        init=init_,
        repr=repr_,
        hash=hash_,
        compare=compare,
        metadata=metadata,
        kw_only=kw_only,
    )
