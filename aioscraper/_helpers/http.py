from http.cookies import SimpleCookie, Morsel, BaseCookie
from typing import Mapping

from yarl import URL

from ..types import QueryParams, RequestCookies


def parse_url(url: str, params: QueryParams | None) -> URL:
    parsed_url = URL(url)
    if params:
        return parsed_url.update_query(params)

    return parsed_url


def to_simple_cookie(cookies: Mapping[str, str]):
    cookie = SimpleCookie()
    for name, value in cookies.items():
        cookie[name] = value

    return cookie


def parse_cookies(v: RequestCookies) -> dict[str, str]:
    cookies: dict[str, str] = {}

    for key, value in v.items():
        if isinstance(value, str):
            cookies[key] = value
        elif isinstance(value, Morsel):
            cookies[value.key] = value.value
        elif isinstance(value, BaseCookie):
            for name, morsel in value.items():
                cookies[name] = morsel.value
        else:
            raise TypeError(f"Unsupported cookie type: {type(value)!r}")

    return cookies
