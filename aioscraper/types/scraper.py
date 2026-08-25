from typing import Any, Awaitable, Callable, Hashable, NamedTuple

from .session import Request

Scraper = Callable[..., Awaitable[Any]]


class GroupPolicy(NamedTuple):
    """How one request is paced and how much of the concurrency its group may take.

    A ``group_by`` may return this or a plain tuple of the same shape.

    Args:
        key (Hashable): What the request is grouped by.
        interval (float): Seconds to wait after handing off one request of the group.
        concurrency (int | None): Ceiling on the group's requests in flight; ``None`` takes
            ``RateLimitConfig.group_concurrency``, ``0`` is no ceiling.
    """

    key: Hashable
    interval: float
    concurrency: int | None = None


GroupBy = Callable[[Request], tuple[Hashable, float, int | None]]
ShouldRetry = Callable[[Request, Exception, int], bool | None]
