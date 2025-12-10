from typing import Awaitable, Callable, Literal

Middleware = Callable[..., Awaitable[None]]
MiddlewareStage = Literal["outer", "inner", "exception", "response"]
