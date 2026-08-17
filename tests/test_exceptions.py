import copy
import pickle
from functools import partial
from typing import Callable

import pytest
from multidict import CIMultiDict, CIMultiDictProxy

from aioscraper.exceptions import (
    AIOScraperException,
    HTTPException,
    ResponseTooLarge,
    StreamConsumed,
    UnsupportedRequestOption,
)

URL = "https://api.test.com/x"


def _http_exception(headers=None) -> HTTPException:
    return HTTPException(URL, "GET", 500, {"X-Trace": "1"} if headers is None else headers, "boom")


# factories rather than instances: each test adds a note to the exception it gets
EXCEPTIONS = (
    pytest.param(_http_exception, id="http"),
    # the aiohttp backend passes the response headers straight through
    pytest.param(partial(_http_exception, CIMultiDictProxy(CIMultiDict([("X-Trace", "1")]))), id="http-multidict"),
    pytest.param(partial(ResponseTooLarge, URL, "GET", 1024), id="too-large"),
    pytest.param(partial(StreamConsumed, URL, "GET"), id="stream-consumed"),
    pytest.param(partial(UnsupportedRequestOption, "httpx", "proxy", "Set SessionConfig.proxy."), id="unsupported"),
)


@pytest.mark.parametrize("build", EXCEPTIONS)
def test_the_message_is_in_args(build: Callable[[], AIOScraperException]):
    exception = build()

    assert exception.args == (str(exception),)


@pytest.mark.parametrize("build", EXCEPTIONS)
def test_survives_pickling(build: Callable[[], AIOScraperException]):
    exception = build()
    exception.add_note("context worth keeping")

    restored = pickle.loads(pickle.dumps(exception))  # noqa: S301

    assert type(restored) is type(exception)
    assert str(restored) == str(exception)
    assert restored.__notes__ == ["context worth keeping"]


@pytest.mark.parametrize("build", EXCEPTIONS)
def test_survives_deepcopy(build: Callable[[], AIOScraperException]):
    exception = build()
    exception.add_note("context worth keeping")

    copied = copy.deepcopy(exception)

    assert str(copied) == str(exception)
    assert copied.__notes__ == ["context worth keeping"]


def test_multidict_headers_keep_duplicates_and_case_insensitive_lookup():
    """aiohttp's proxy does not pickle, and collapsing it to a dict would lose both."""
    headers = CIMultiDictProxy(CIMultiDict([("Set-Cookie", "a=1"), ("Set-Cookie", "b=2"), ("Retry-After", "5")]))
    exception = _http_exception(headers)

    restored = pickle.loads(pickle.dumps(exception))  # noqa: S301

    assert restored.headers.getall("Set-Cookie") == ["a=1", "b=2"]
    assert restored.headers.get("retry-after") == "5"


def test_plain_headers_are_left_alone():
    exception = _http_exception({"X-Trace": "1"})

    restored = pickle.loads(pickle.dumps(exception))  # noqa: S301

    assert restored.headers == {"X-Trace": "1"}


def test_http_exception_keeps_its_fields():
    exception = HTTPException(URL, "POST", 503, {"Retry-After": "5"}, "unavailable")

    assert exception.url == URL
    assert exception.method == "POST"
    assert exception.status_code == 503
    assert exception.headers == {"Retry-After": "5"}
    assert exception.message == "unavailable"
    assert str(exception) == "POST https://api.test.com/x: 503: unavailable"
