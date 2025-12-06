from typing import Callable

from ..types import Middleware, MiddlewareStage


class MiddlewareHolder:
    "Stores request/response middlewares and provides decorator-style registration."

    def __init__(self):
        self.outer = []
        self.inner = []
        self.exception = []
        self.response = []

    def __call__(self, middleware_type: MiddlewareStage) -> Callable[[Middleware], Middleware]:
        "Return a decorator that registers a middleware under the given type."

        def decorator(middleware: Middleware) -> Middleware:
            self.add(middleware_type, middleware)
            return middleware

        return decorator

    def add(self, middleware_type: MiddlewareStage, *middlewares: Middleware):
        "Append middlewares to the appropriate bucket."
        match middleware_type:
            case "outer":
                self.outer.extend(middlewares)
            case "inner":
                self.inner.extend(middlewares)
            case "exception":
                self.exception.extend(middlewares)
            case "response":
                self.response.extend(middlewares)
            case _:
                raise ValueError(f"Unsupported request middleware type: {middleware_type}")
