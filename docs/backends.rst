HTTP backends
=============

`aioscraper` runs on ``aiohttp``, ``httpx`` or ``httpx2``. The choice is made once, when the session is built: ``aiohttp`` is used when installed, then ``httpx``, then ``httpx2``. Force one with :class:`SessionConfig.http_backend <aioscraper.config.models.SessionConfig>` (``SESSION_HTTP_BACKEND``), or by passing a client of that library as :ref:`http_client <own-http-client>`.

Everything the framework does itself - queueing, priorities, retries, rate limiting, body limits, middlewares, pipelines, the shape of :class:`Response <aioscraper.types.session.Response>` - is identical on all of them. The differences below are the ones the client libraries impose. ``httpx2`` is a fork of ``httpx`` 0.28.1 and behaves as the ``httpx`` column describes; :ref:`httpx2 <httpx2-backend>` covers what it does differently.

Request fields
--------------

.. list-table::
   :header-rows: 1
   :widths: 22 39 39

   * - :class:`Request <aioscraper.types.session.Request>` field
     - aiohttp
     - httpx
   * - ``proxy``
     - Applied per request; takes precedence over ``session.proxy``.
     - :class:`UnsupportedRequestOption <aioscraper.exceptions.UnsupportedRequestOption>`; httpx resolves proxies per transport, so use ``session.proxy``.
   * - ``proxy_auth``
     - Applied per request.
     - ``UnsupportedRequestOption``; embed the credentials in the ``session.proxy`` URL.
   * - ``proxy_headers``
     - Applied per request.
     - ``UnsupportedRequestOption``.
   * - ``max_redirects``
     - Applied per request.
     - Not applied: the limit belongs to the client - ``10`` for the one `aioscraper` builds, whatever it was built with for a provided one. Any value other than the ``Request`` default raises ``UnsupportedRequestOption`` unless ``allow_redirects`` is ``False``.
   * - ``timeout``
     - Total budget for the request; falls back to ``session.timeout``.
     - Applied to each of connect, read, write and pool separately, so a request can take longer than the value; falls back to ``session.timeout``.
   * - ``auth``
     - Credentials are encoded with ``BasicAuth.encoding``, Latin-1 by default.
     - Credentials are encoded as UTF-8; an ``encoding`` that means anything else raises ``UnsupportedRequestOption`` rather than being ignored. A name no codec answers to is rejected before any backend sees it, as :class:`InvalidRequestData <aioscraper.exceptions.InvalidRequestData>`, whether the request carried it from the start or a middleware set it.
   * - ``allow_redirects``, ``params``, ``headers``, ``cookies``, ``data``, ``json_data``, ``files``
     - Applied per request.
     - Same.

Session settings
----------------

.. list-table::
   :header-rows: 1
   :widths: 22 39 39

   * - :class:`SessionConfig <aioscraper.config.models.SessionConfig>` field
     - aiohttp
     - httpx
   * - ``proxy``
     - A single URL for every request.
     - A single URL, or a per-scheme mapping mounted on separate transports.
   * - ``ssl``
     - A ``bool`` or an ``SSLContext`` on the connector.
     - The same value as httpx's ``verify``.
   * - ``timeout``
     - Total budget for the request.
     - The same number for each of connect, read, write and pool, which is not a budget for the request as a whole.
   * - ``max_response_body_size``, ``max_error_body_size``, ``retry``, ``rate_limit``
     - Enforced by the framework, not the client.
     - Same.

Behavior
--------

- **Redirects.** The httpx client is pinned to the ``Request.max_redirects`` default so every backend follows the same number of them; httpx would otherwise use its own default of 20.
- **Response bodies.** All of them stream: aiohttp through ``content.iter_chunked``, httpx through a ``stream=True`` send closed with the request context. :meth:`iter_bytes() <aioscraper.types.session.Response.iter_bytes>` and :meth:`read() <aioscraper.types.session.Response.read>` behave the same everywhere.
- **Cookies.** ``Response.cookies`` is a ``SimpleCookie`` on every backend; httpx's own cookie jar is converted.
- **URLs.** ``params`` extend the query the URL already carries on every backend, so ``?tag=old`` with ``params={"tag": "new"}`` is sent as ``?tag=old&tag=new``. On httpx they are merged into the URL before the request is built.

An injected client keeps its own timeout, SSL, proxy and redirect settings, so the second table no longer describes it, and neither does the redirect limit above. The per-request fields are applied to it as they are to any client, ``Request.timeout`` included.

.. _httpx2-backend:

httpx2
------

`httpx2 <https://github.com/pydantic/httpx2>`_ is a fork of ``httpx`` 0.28.1, maintained by Pydantic, on its own ``httpcore2``. It supports the httpx APIs `aioscraper` uses, so both tables above apply to it as written, including every ``UnsupportedRequestOption``: proxies are still resolved per transport there, and the redirect limit still belongs to the client.

What differs from ``httpx`` itself:

- **Trust store.** ``ssl=True`` verifies against the certificates of the operating system through ``truststore``, where ``httpx`` uses the ones bundled in ``certifi``.
- **Separate package.** ``httpx`` and ``httpx2`` can be installed side by side, and their clients, sentinels and exception classes are unrelated. ``httpx2.AsyncClient`` selects the ``httpx2`` backend, and ``http_backend="httpx"`` with such a client is rejected rather than silently honored. Code that catches client exceptions must catch the ones of the package in use.
- **HTTP/2.** Available with the ``http2`` extra of the package, which ``aiohttp`` has no equivalent of. `aioscraper` builds its client with the default of HTTP/1.1; pass your own ``httpx2.AsyncClient(http2=True)`` as ``http_client`` to use it.
