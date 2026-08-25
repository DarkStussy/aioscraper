from typing import Any, Awaitable, Callable, Hashable

from .session import Request

Scraper = Callable[..., Awaitable[Any]]

GroupBy = Callable[[Request], tuple[Hashable, float]]
ShouldRetry = Callable[[Request, Exception, int], bool | None]
