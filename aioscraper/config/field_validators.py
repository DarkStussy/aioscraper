import re
from collections.abc import Callable
from decimal import Decimal
from math import isfinite
from typing import Any, Generic, Iterable, Protocol, TypeVar

from yarl import URL

T = TypeVar("T")


class Validator(Protocol[T]):
    "Checks one config field, and may return a normalized value in place of the original."

    def __call__(self, key: str, value: T) -> T:
        """Return the value to keep, or raise ``ValueError`` naming ``key``."""
        ...


NumericT = TypeVar("NumericT", int, float, Decimal)


class RangeValidator(Generic[NumericT]):
    """
    Bounds a number, inclusive on both ends. ``None`` passes, ``NaN`` and infinity never do.

    Args:
        min_value: Lowest accepted value; ``None`` leaves it unbounded below.
        max_value: Highest accepted value; ``None`` leaves it unbounded above.
    """

    def __init__(self, min_value: NumericT | None = None, max_value: NumericT | None = None):
        if min_value is None and max_value is None:
            raise ValueError("At least one of min or max must be specified")

        self.min_value = min_value
        self.max_value = max_value

    def __call__(self, key: str, value: NumericT | None) -> NumericT | None:
        if value is None:
            return value

        # NaN passes every comparison below, and infinity passes the ones that are set
        if not isfinite(value):
            raise ValueError(f"Value for {key} is {value}, but must be finite")

        if self.min_value is not None and value < self.min_value:
            raise ValueError(f"Value for {key} is {value}, but minimum is {self.min_value}")
        if self.max_value is not None and value > self.max_value:
            raise ValueError(f"Value for {key} is {value}, but maximum is {self.max_value}")

        return value


class LengthValidator:
    "Bounds the length of a string, list or tuple, inclusive on both ends."

    def __init__(self, *, min_length: int | None = None, max_length: int | None = None):
        if min_length is None and max_length is None:
            raise ValueError("At least one of min or max must be specified")
        if min_length is not None and min_length < 0:
            raise ValueError("min must be non-negative")
        if max_length is not None and max_length < 0:
            raise ValueError("max must be non-negative")
        if min_length is not None and max_length is not None and min_length > max_length:
            raise ValueError("min cannot be greater than max")

        self.min_length = min_length
        self.max_length = max_length

    def __call__(self, key: str, value: str | list[Any] | tuple[Any, ...]) -> str | list[Any] | tuple[Any, ...]:
        length = len(value)
        if self.min_length is not None and length < self.min_length:
            raise ValueError(f"Length of {key} is {length}, but minimum is {self.min_length}")
        if self.max_length is not None and length > self.max_length:
            raise ValueError(f"Length of {key} is {length}, but maximum is {self.max_length}")

        return value


class RegexValidator:
    """
    Requires a string to match a pattern from its start, as ``re.match`` does.

    Args:
        pattern (str): The pattern to match.
        flags (int): Flags to compile it with, such as ``re.IGNORECASE``.
    """

    def __init__(self, pattern: str, flags: int = 0):
        self.pattern = pattern
        self.regex = re.compile(pattern, flags)

    def __call__(self, key: str, value: str) -> str:
        if not self.regex.match(value):
            raise ValueError(f"Value for {key} does not match pattern {self.pattern!r}")

        return value


class ChoicesValidator(Generic[T]):
    "Requires the value to be one of a fixed set."

    def __init__(self, choices: set[T] | list[T]):
        self.choices = set(choices) if isinstance(choices, list) else choices

    def __call__(self, key: str, value: T) -> T:
        if value not in self.choices:
            raise ValueError(f"Value for {key} is {value!r}, but must be one of {self.choices}")

        return value


class CustomValidator(Generic[T]):
    "Defers to a function. ``True`` keeps the value, ``False`` rejects it, anything else replaces it."

    def __init__(self, func: Callable[[Any], bool | T]):
        self._func = func

    def __call__(self, key: str, value: T) -> T:
        try:
            result = self._func(value)
        except Exception as e:
            raise ValueError(f"Custom validation failed for {key}: {e}") from e
        else:
            if result is False:
                raise ValueError(f"Custom validation failed for {key}")
            if result is True:
                return value

            return result


class ChainValidator(Generic[T]):
    "Runs validators in order, each seeing what the previous one returned."

    def __init__(self, validators: Iterable[Validator[T]]):
        if not validators:
            raise ValueError("At least one validator must be provided")

        self._validators = validators

    def __call__(self, key: str, value: T) -> T:
        for validator in self._validators:
            value = validator(key, value)

        return value


class ProxyValidator:
    """
    Checks a proxy setting, which is either ``None``, one URL, or a URL per scheme.

    A mapping comes back keyed as httpx mounts want it - ``"http"`` becomes ``"http://"``. Every
    URL must carry a scheme the constructor was given.
    """

    def __init__(self, valid_schemes: set[str]):
        self._valid_schemes = valid_schemes

    def __call__(self, key: str, value: str | dict[str, str | None] | None) -> str | dict[str, str | None] | None:
        if value is None:
            return None

        if isinstance(value, str):
            try:
                parsed = URL(value)
            except Exception as e:
                raise ValueError(f"Invalid proxy URL for {key}: {value!r}") from e
            else:
                if not parsed.scheme or parsed.scheme not in self._valid_schemes:
                    raise ValueError("Proxy URL must include a scheme (e.g., http, https)")

                return value

        if isinstance(value, dict):
            for scheme, proxy_url in value.items():
                if scheme not in self._valid_schemes:
                    raise ValueError(f"Invalid proxy scheme in {key}: {scheme!r}. Must be one of {self._valid_schemes}")

                if proxy_url is not None:
                    try:
                        parsed = URL(proxy_url)
                    except Exception as e:
                        raise ValueError(f"Invalid proxy URL for scheme {scheme} in {key}: {proxy_url!r}") from e
                    else:
                        if not parsed.scheme or parsed.scheme not in self._valid_schemes:
                            raise ValueError("Proxy URL must include a scheme (e.g., http, https)")

            return {f"{k}://": v for k, v in value.items()}

        raise TypeError(f"Proxy for {key} must be None, str, or dict[str, str | None], got {type(value)}")
