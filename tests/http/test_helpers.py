from http.cookies import Morsel, SimpleCookie

import pytest

from aioscraper._helpers.http import parse_cookies, parse_url, to_simple_cookie


def test_parse_url_updates_query_params():
    url = parse_url("https://example.com/path?q0=1", {"q1": "2"})

    assert str(url) == "https://example.com/path?q0=1&q1=2"


def test_parse_url_without_params_keeps_original():
    url = parse_url("https://example.com/path", None)

    assert str(url) == "https://example.com/path"


def test_to_simple_cookie_builds_cookie():
    cookie = to_simple_cookie({"a": "1", "b": "2"})

    assert isinstance(cookie, SimpleCookie)
    assert cookie["a"].value == "1"
    assert cookie["b"].value == "2"


def test_parse_cookies_supports_str_morsel_and_basecookie():
    morsel = Morsel()
    morsel.set("b", "2", "2")
    base_cookie = SimpleCookie()
    base_cookie["c"] = "3"

    parsed = parse_cookies({"a": "1", "b": morsel, "c": base_cookie})

    assert parsed == {"a": "1", "b": "2", "c": "3"}


def test_parse_cookies_rejects_unknown_type():
    with pytest.raises(TypeError):
        parse_cookies({"a": object()})  # type: ignore[reportArgumentType]
