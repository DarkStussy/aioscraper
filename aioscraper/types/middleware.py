from typing import Awaitable, Callable


Middleware = Callable[..., Awaitable[None]]
ExceptionMiddleware = Callable[..., Awaitable[bool | None]]
