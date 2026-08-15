import pytest

from aioscraper.exceptions import ResponseTooLarge, StreamConsumed
from tests.mocks import make_response


async def test_read_buffers_the_body_and_can_be_repeated():
    calls: list[int] = []
    response = make_response(b"payload", calls=calls)

    assert await response.read() == b"payload"
    assert await response.read() == b"payload"
    assert sum(calls) == len(b"payload")  # the stream was pulled once


async def test_read_rejects_a_body_over_the_limit():
    response = make_response(b"x" * 100, max_body_size=64)

    with pytest.raises(ResponseTooLarge) as excinfo:
        await response.read()

    assert excinfo.value.limit == 64


async def test_read_accepts_a_body_at_the_limit():
    response = make_response(b"x" * 64, max_body_size=64)

    assert len(await response.read()) == 64


async def test_iter_bytes_streams_in_chunks():
    response = make_response(b"0123456789")

    assert [chunk async for chunk in response.iter_bytes(4)] == [b"0123", b"4567", b"89"]


async def test_iter_bytes_stops_at_the_limit_before_buffering_the_rest():
    calls: list[int] = []
    response = make_response(b"x" * 4096, max_body_size=1024, calls=calls)

    with pytest.raises(ResponseTooLarge):
        async for _ in response.iter_bytes(512):
            pass

    # the iterator is abandoned at the first chunk crossing the limit, not drained
    assert sum(calls) == 1536


async def test_iter_bytes_replays_a_buffered_body():
    calls: list[int] = []
    response = make_response(b"0123456789", calls=calls)

    await response.read()

    assert [chunk async for chunk in response.iter_bytes(4)] == [b"0123", b"4567", b"89"]
    assert sum(calls) == 10  # replayed from memory, the stream was not pulled again


async def test_read_after_streaming_raises():
    response = make_response(b"payload")

    async for _ in response.iter_bytes():
        pass

    with pytest.raises(StreamConsumed):
        await response.read()


async def test_iter_bytes_twice_raises():
    response = make_response(b"payload")

    async for _ in response.iter_bytes():
        pass

    with pytest.raises(StreamConsumed):
        async for _ in response.iter_bytes():
            pass


async def test_early_break_leaves_the_stream_consumed():
    response = make_response(b"x" * 4096)

    async for _ in response.iter_bytes(512):
        break

    with pytest.raises(StreamConsumed):
        await response.read()


async def test_limited_read_returns_a_prefix():
    calls: list[int] = []
    response = make_response(b"0123456789", calls=calls)

    assert await response.read(limit=4) == b"0123"
    assert sum(calls) == 4  # stopped at the limit instead of draining the body


async def test_limited_read_is_capped_by_the_body_limit():
    calls: list[int] = []
    response = make_response(b"0123456789", max_body_size=4, calls=calls)

    assert await response.read(limit=50) == b"0123"
    assert sum(calls) == 4


async def test_limited_read_consumes_the_stream():
    response = make_response(b"0123456789")

    await response.read(limit=4)

    with pytest.raises(StreamConsumed):
        await response.read()


async def test_limited_read_of_a_buffered_body_keeps_the_buffer():
    response = make_response(b"0123456789")

    await response.read()

    assert await response.read(limit=4) == b"0123"
    assert await response.read() == b"0123456789"


async def test_limited_read_of_zero_leaves_the_stream_untouched():
    calls: list[int] = []
    response = make_response(b"0123456789", calls=calls)

    assert await response.read(limit=0) == b""
    assert not calls
    assert await response.read() == b"0123456789"


async def test_text_and_json_read_the_whole_body():
    assert await make_response(b'{"ok": true}').text() == '{"ok": true}'
    assert await make_response(b'{"ok": true}').json() == {"ok": True}
