class RunStats:
    "Counters behind :class:`RunResult <aioscraper.core.errors.RunResult>`, which defines what each one means."

    __slots__ = ("_items_processed", "_requests_failed", "_requests_started", "_requests_succeeded")

    def __init__(self):
        self._requests_started = 0
        self._requests_succeeded = 0
        self._requests_failed = 0
        self._items_processed = 0

    @property
    def requests_started(self) -> int:
        "Attempts handed to the middleware chain."
        return self._requests_started

    @property
    def requests_succeeded(self) -> int:
        "Attempts whose response was returned by the chain and processed by the callback."
        return self._requests_succeeded

    @property
    def requests_failed(self) -> int:
        "Attempts that ended in an exception and were not retried."
        return self._requests_failed

    @property
    def items_processed(self) -> int:
        "Items the pipeline dispatcher handled without raising."
        return self._items_processed

    def request_started(self):
        self._requests_started += 1

    def request_succeeded(self):
        self._requests_succeeded += 1

    def request_failed(self):
        self._requests_failed += 1

    def item_processed(self):
        self._items_processed += 1
