import logging
from typing import Iterator

from aioscraper._helpers.log import get_log_name
from aioscraper.types import RequestMiddlewareFactory

logger = logging.getLogger(__name__)


class MiddlewareHolder:
    "Stores request middleware factories in registration order."

    def __init__(self):
        self._factories: list[RequestMiddlewareFactory] = []

    def __call__(self, factory: RequestMiddlewareFactory) -> RequestMiddlewareFactory:
        "Decorator form: register a middleware factory."
        self.add(factory)
        return factory

    def add(self, *factories: RequestMiddlewareFactory):
        """
        Register request middleware factories in order.

        Each factory can accept injected dependencies and must return a middleware with signature
        ``async def mw(call_next, request): ...`` which wraps the request handler chain for every
        request..
        """
        for factory in factories:
            logger.debug("Installing request middleware factory %s", get_log_name(factory))
            self._factories.append(factory)

    def __iter__(self) -> Iterator[RequestMiddlewareFactory]:
        return iter(self._factories)

    def __len__(self) -> int:
        return len(self._factories)
