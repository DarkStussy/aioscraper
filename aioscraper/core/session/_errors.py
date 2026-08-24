import asyncio
import ssl
from contextlib import asynccontextmanager, contextmanager
from typing import AsyncIterator, Callable, Iterator

from aioscraper.exceptions import ClientException, TLSError, TransportTimeout, _RequestFailure

# every class it can name takes (url, method, message)
Classifier = Callable[[BaseException], type[ClientException] | None]
AiterBytes = Callable[[int], AsyncIterator[bytes]]

_MAX_CAUSE_DEPTH = 8


def causes(exc: BaseException) -> Iterator[BaseException]:
    "``exc`` and the exceptions it was raised from."
    current: BaseException | None = exc
    for _ in range(_MAX_CAUSE_DEPTH):
        if current is None:
            return

        yield current
        # __context__ too: a client wrapping an error of its own transport layer does not always
        # chain it explicitly
        current = current.__cause__ or current.__context__


def caused_by(exc: BaseException, *types: type[BaseException]) -> bool:
    return any(isinstance(cause, types) for cause in causes(exc))


def classify_tls(exc: BaseException) -> type[ClientException] | None:
    return TLSError if caused_by(exc, ssl.SSLError) else None


def deadline_for(request_timeout: float | None, session_timeout: float | None) -> float | None:
    "Loop-clock instant the response must be complete by."
    budget = request_timeout if request_timeout is not None else session_timeout
    return None if budget is None else asyncio.get_running_loop().time() + budget


@asynccontextmanager
async def within_deadline(deadline: float | None, url: str, method: str) -> AsyncIterator[None]:
    "Hold the budget ourselves: httpx times each phase, so a drip-fed body never reaches a limit."
    if deadline is None:
        yield
        return

    try:
        async with asyncio.timeout_at(deadline):
            yield
    except TimeoutError as exc:
        raise TransportTimeout(url, method, "timed out") from exc


@contextmanager
def client_errors(classify: Classifier, url: str, method: str) -> Iterator[None]:
    "Re-raise what the client raised as its backend-neutral equivalent, chaining the original."
    try:
        yield
    except _RequestFailure:
        raise
    except Exception as exc:
        error_type = classify(exc)
        if error_type is None:
            raise

        # str() of a client exception is often empty: aiohttp's disconnects, httpx's read errors
        raise error_type(url, method, str(exc) or type(exc).__name__) from exc


def guard_stream(
    aiter_bytes: AiterBytes,
    classify: Classifier,
    url: str,
    method: str,
    deadline: float | None = None,
) -> AiterBytes:
    "Wrap a body iterator: a failure mid-stream is translated, and the budget covers the body too."

    async def guarded(chunk_size: int) -> AsyncIterator[bytes]:
        # driven by hand rather than with `async for`: a translation around the yield would also
        # catch what the consumer of the chunk raises
        with client_errors(classify, url, method):
            iterator = aiter_bytes(chunk_size).__aiter__()

        while True:
            with client_errors(classify, url, method):
                try:
                    async with within_deadline(deadline, url, method):
                        chunk = await anext(iterator)
                except StopAsyncIteration:
                    return

            yield chunk

    return guarded
