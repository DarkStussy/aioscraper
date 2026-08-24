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

    Requests are counted per attempt, and only the attempt that ends a request counts as succeeded
    or failed: ``requests_succeeded`` and ``requests_failed`` therefore add up to
    ``requests_started`` minus the attempts that were retried, that a middleware handled on its own,
    and that a shutdown cut short.

    Attributes:
        errors (tuple[ScraperError, ...]): The most recent unhandled errors, capped by the collector.
        error_counts (Mapping[str, int]): Exact number of unhandled errors per context.
        interrupted (bool): SIGINT/SIGTERM stopped the run.
        timed_out (bool): ``execution.timeout`` expired before the run finished.
        requests_started (int): Attempts handed to the middleware chain.
        requests_succeeded (int): Attempts whose response was returned by the chain and processed
            by the callback.
        requests_failed (int): Attempts that ended in an exception and were not retried. Counted
            whether or not an ``errback`` handled it, unlike ``error_counts``; ``ok`` therefore
            stays ``True`` for a handled failure, and ``all_requests_succeeded`` does not.
        items_processed (int): Items the pipeline dispatcher handled without raising.
    """

    errors: tuple[ScraperError, ...] = ()
    error_counts: Mapping[str, int] = field(default_factory=dict)
    interrupted: bool = False
    timed_out: bool = False
    requests_started: int = 0
    requests_succeeded: int = 0
    requests_failed: int = 0
    items_processed: int = 0

    @property
    def total_errors(self) -> int:
        "How many unhandled errors the run recorded."
        return sum(self.error_counts.values())

    @property
    def ok(self) -> bool:
        "Whether the run finished on its own with nothing unhandled recorded. A handled failure keeps it ``True``."
        return not self.error_counts and not self.interrupted and not self.timed_out

    @property
    def all_requests_succeeded(self) -> bool:
        "Whether no request ended in failure, handled or not. A failure a retry recovered from is not one."
        return self.requests_failed == 0


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
