from collections import Counter, deque
from dataclasses import dataclass
from logging import getLogger
from typing import Mapping

logger = getLogger(__name__)

DEFAULT_MAX_RETAINED_ERRORS = 100


@dataclass(slots=True, frozen=True)
class ScraperError:
    """An error that was handled internally instead of reaching the caller.

    Attributes:
        context (str): Where the error came from, e.g. ``"request"`` or ``"close"``.
        exception (BaseException): The original exception.
    """

    context: str
    exception: BaseException


class ErrorCollector:
    """Records errors that were logged and dropped: unhandled request exceptions,
    failing errbacks, resources that would not close.

    Counts are exact. Retained exceptions are capped because each one keeps its
    traceback, and therefore the frames it references, alive.

    Args:
        max_retained (int): How many exception objects to keep. ``0`` keeps none.
    """

    def __init__(self, max_retained: int = DEFAULT_MAX_RETAINED_ERRORS):
        self._counts: Counter[str] = Counter()
        self._retained: deque[ScraperError] = deque(maxlen=max_retained)

    def __len__(self) -> int:
        return self.total

    def __bool__(self) -> bool:
        return bool(self._counts)

    @property
    def total(self) -> int:
        "How many errors were recorded, including the ones no longer retained."
        return sum(self._counts.values())

    @property
    def counts(self) -> Mapping[str, int]:
        "Exact number of errors per context."
        return dict(self._counts)

    @property
    def errors(self) -> tuple[ScraperError, ...]:
        "The most recent errors, capped at ``max_retained``."
        return tuple(self._retained)

    def record(self, context: str, exception: BaseException):
        """Record a swallowed error.

        Args:
            context (str): Where the error came from.
            exception (BaseException): The original exception.
        """
        self._counts[context] += 1
        self._retained.append(ScraperError(context=context, exception=exception))

    def clear(self):
        "Drop every recorded error."
        self._counts.clear()
        self._retained.clear()
