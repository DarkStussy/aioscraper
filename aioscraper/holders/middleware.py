from collections.abc import Iterable
from typing import Callable

from ..types import Middleware, MiddlewareStage


class MiddlewareHolder:
    "Stores request/response middlewares and provides decorator-style registration."

    def __init__(self):
        self._outer: list[tuple[int, Middleware]] = []
        self._inner: list[tuple[int, Middleware]] = []
        self._exception: list[tuple[int, Middleware]] = []
        self._response: list[tuple[int, Middleware]] = []

    def __call__(self, middleware_type: MiddlewareStage, *, priority: int = 0) -> Callable[[Middleware], Middleware]:
        "Return a decorator that registers a middleware under the given type and priority."

        def decorator(middleware: Middleware) -> Middleware:
            self.add(middleware_type, middleware, priority=priority)
            return middleware

        return decorator

    def add(self, middleware_type: MiddlewareStage, *middlewares: Middleware, priority: int = 100):
        "Append middlewares to the appropriate bucket."
        bucket = self._get_bucket(middleware_type)

        for middleware in middlewares:
            bucket.append((priority, middleware))

        bucket.sort(key=lambda item: item[0])

    @property
    def outer(self) -> Iterable[Middleware]:
        for _, middleware in self._outer:
            yield middleware

    @property
    def inner(self) -> Iterable[Middleware]:
        for _, middleware in self._inner:
            yield middleware

    @property
    def exception(self) -> Iterable[Middleware]:
        for _, middleware in self._exception:
            yield middleware

    @property
    def response(self) -> Iterable[Middleware]:
        for _, middleware in self._response:
            yield middleware

    def _get_bucket(self, middleware_type: MiddlewareStage) -> list[tuple[int, Middleware]]:
        match middleware_type:
            case "outer":
                return self._outer
            case "inner":
                return self._inner
            case "exception":
                return self._exception
            case "response":
                return self._response
            case _:
                raise ValueError(f"Unsupported request middleware type: {middleware_type}")
