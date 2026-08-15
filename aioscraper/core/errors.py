from collections import Counter, deque
from dataclasses import dataclass, field
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


@dataclass(slots=True, frozen=True)
class RunResult:
    """The outcome of a finished run.

    Attributes:
        errors (tuple[ScraperError, ...]): The most recent unhandled errors, capped by the collector.
        error_counts (Mapping[str, int]): Exact number of unhandled errors per context.
        interrupted (bool): SIGINT/SIGTERM stopped the run.
        timed_out (bool): ``execution.timeout`` expired before the run finished.
    """

    errors: tuple[ScraperError, ...] = ()
    error_counts: Mapping[str, int] = field(default_factory=dict)
    interrupted: bool = False
    timed_out: bool = False

    @property
    def total_errors(self) -> int:
        "How many unhandled errors the run recorded."
        return sum(self.error_counts.values())

    @property
    def ok(self) -> bool:
        "Whether the run finished on its own with nothing recorded."
        return not self.error_counts and not self.interrupted and not self.timed_out


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
