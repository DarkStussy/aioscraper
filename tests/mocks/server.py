import asyncio
import inspect
import math
import re
from contextlib import AbstractContextManager, ExitStack
from dataclasses import dataclass
from http import HTTPStatus
from typing import Any, Callable, Self

from aiohttp import web
from aiohttp.test_utils import BaseTestServer
from aiohttp.web_runner import ServerRunner
from aiohttp.web_server import Server
from yarl import URL

from aioscraper.types.stub import NotSetType

NOTSET = NotSetType()


@dataclass(slots=True, kw_only=True)
class MockResponse:
    status: int = HTTPStatus.OK
    text: str | None = None
    json: Any = NOTSET
    headers: dict[str, str] | None = None

    def __post_init__(self):
        if self.json is not NOTSET and self.text:
            raise ValueError("Cannot set both json and text")


ResponseHandler = Callable[[web.BaseRequest], Any]


def _parse_url_without_scheme_and_qs(v: str) -> str:
    url = URL(v)
    host = url.host
    port = f":{url.port}" if url.port not in (None, 80, 443) else ""
    path = url.path
    return f"{host}{port}{path}"


@dataclass(slots=True, kw_only=True)
class Route:
    method: str
    url: str | re.Pattern[str]
    handler: ResponseHandler
    repeat: int = 1
    called: int = 0

    def matches(self, method: str, url: str) -> bool:
        if method.upper() != self.method:
            return False

        return bool(re.fullmatch(self.url, _parse_url_without_scheme_and_qs(url)))


class MockServer(BaseTestServer):
    def __init__(
        self,
        patch_client: Callable[[int], AbstractContextManager],
        *,
        scheme: str = "",
        host: str = "127.0.0.1",
        port: int = 0,
    ):
        super().__init__(scheme=scheme, host=host, port=port)
        self._calls: list[tuple[str, str, MockResponse | web.StreamResponse]] = []
        self._routes: list[Route] = []
        self._unmatched: list[web.BaseRequest] = []
        self._patch_client = patch_client
        self._patch_exit_stack = ExitStack()

    async def _make_runner(self, *, debug: bool = True, **kwargs):
        srv = Server(self._dispatch, loop=self._loop, debug=True, **kwargs)
        return ServerRunner(srv, debug=debug, **kwargs)

    async def _dispatch(self, request: web.BaseRequest) -> web.StreamResponse:
        method = request.method.upper()
        for route in self._routes:
            if route.called >= route.repeat or not route.matches(request.method, str(request.url)):
                continue

            route.called += 1

            if inspect.iscoroutinefunction(route.handler):
                response = await route.handler(request)
            else:
                response = await asyncio.to_thread(route.handler, request)

            if isinstance(response, web.StreamResponse):
                self._calls.append((method, request.path, response))
                return response

            if not isinstance(response, MockResponse):
                response = MockResponse(json=response)

            self._calls.append((method, request.path, response))

            if response.json is not NOTSET:
                return web.json_response(data=response.json, status=response.status, headers=response.headers)

            return web.Response(text=response.text, status=response.status, headers=response.headers)

        self._unmatched.append(request)
        raise web.HTTPNotFound

    async def __aenter__(self) -> Self:
        await self.start_server(loop=self._loop)
        self._patch_exit_stack.enter_context(self._patch_client(self.port or 0))
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self._patch_exit_stack.__exit__(exc_type, exc_val, exc_tb)
        await self.close()

    def add(
        self,
        url: str | re.Pattern[str],
        *,
        method: str = "GET",
        handler: ResponseHandler | None = None,
        repeat: int = 1,
    ):
        self._routes.append(
            Route(
                url=_parse_url_without_scheme_and_qs(url) if isinstance(url, str) else url,
                method=method.upper(),
                handler=handler or (lambda _: MockResponse()),
                repeat=repeat,
            ),
        )

    def assert_no_unused_routes(self, *, ignore_infinite_repeats: bool = False):
        unused = [
            route
            for route in self._routes
            if route.called < route.repeat and not (ignore_infinite_repeats and route.repeat == math.inf)
        ]
        if unused:
            details = ", ".join(f"{route.method} {route.url} ({route.called}/{route.repeat})" for route in unused)
            raise AssertionError(f"Unused routes: {details}")

    def assert_all_requests_matched(self):
        for request in self._unmatched:
            raise AssertionError(f"No match found for request: {request.method} {request.host} {request.path}")

    def assert_all_routes_handled(self):
        self.assert_no_unused_routes()
        self.assert_all_requests_matched()
