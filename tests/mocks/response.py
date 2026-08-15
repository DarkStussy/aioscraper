from http.cookies import SimpleCookie
from typing import AsyncIterator, Callable

from aioscraper.types import Response


def byte_stream(body: bytes, *, calls: list[int] | None = None) -> Callable[[int], AsyncIterator[bytes]]:
    "Build a backend-style body iterator over ``body``, recording every yielded chunk size in ``calls``."

    async def _iter(chunk_size: int) -> AsyncIterator[bytes]:
        for start in range(0, len(body), chunk_size):
            chunk = body[start : start + chunk_size]
            if calls is not None:
                calls.append(len(chunk))

            yield chunk

    return _iter


def make_response(
    body: bytes = b"",
    *,
    url: str = "https://api.test.com/resource",
    method: str = "GET",
    status: int = 200,
    headers: dict[str, str] | None = None,
    max_body_size: int | None = None,
    calls: list[int] | None = None,
) -> Response:
    "Build a :class:`Response` streaming ``body`` from memory; ``calls`` collects the chunk sizes pulled."
    return Response(
        url=url,
        method=method,
        status=status,
        headers={"Content-Type": "text/plain; charset=utf-8"} if headers is None else headers,
        cookies=SimpleCookie(),
        aiter_bytes=byte_stream(body, calls=calls),
        max_body_size=max_body_size,
    )
