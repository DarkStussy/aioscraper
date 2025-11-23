from typing import Any, Awaitable, Callable


Scraper = Callable[..., Awaitable[Any]]
Middleware = Callable[..., Awaitable[None]]
