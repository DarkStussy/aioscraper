from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from http import HTTPStatus
from http.cookies import BaseCookie, Morsel, SimpleCookie
from typing import Mapping

from yarl import URL

from aioscraper.exceptions import HTTPException
from aioscraper.types import QueryParams, RequestCookies


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


def parse_retry_after(exc: Exception) -> float | None:
    "Parse Retry-After header from HTTPException."
    if not isinstance(exc, HTTPException) or exc.status_code not in (
        HTTPStatus.TOO_MANY_REQUESTS,
        HTTPStatus.SERVICE_UNAVAILABLE,
    ):
        return None

    retry_after = exc.headers.get("Retry-After") or exc.headers.get("retry-after")
    if not retry_after:
        return None

    try:
        return float(retry_after)
    except ValueError:
        pass

    try:
        retry_date = parsedate_to_datetime(retry_after)
        now = datetime.now(UTC)
        delay = (retry_date - now).total_seconds()
        return max(0.0, delay)
    except (ValueError, TypeError):
        return None
