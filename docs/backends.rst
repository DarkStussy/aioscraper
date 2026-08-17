HTTP backends
=============

`aioscraper` runs on ``aiohttp`` or ``httpx``. The choice is made once, when the session is built: ``aiohttp`` is used when installed, otherwise ``httpx``. Force one with :class:`SessionConfig.http_backend <aioscraper.config.models.SessionConfig>` (``SESSION_HTTP_BACKEND``), or by passing a client of that library as :ref:`http_client <own-http-client>`.

Everything the framework does itself - queueing, priorities, retries, rate limiting, body limits, middlewares, pipelines, the shape of :class:`Response <aioscraper.types.session.Response>` - is identical on both. The differences below are the ones the client libraries impose.

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
     - Credentials are encoded as UTF-8; an ``encoding`` that means anything else raises ``UnsupportedRequestOption`` rather than being ignored. A name no codec answers to is rejected before either backend sees it, as :class:`InvalidRequestData <aioscraper.exceptions.InvalidRequestData>`, whether the request carried it from the start or a middleware set it.
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

- **Redirects.** The httpx client is pinned to the ``Request.max_redirects`` default so both backends follow the same number of them; httpx would otherwise use its own default of 20.
- **Response bodies.** Both stream: aiohttp through ``content.iter_chunked``, httpx through a ``stream=True`` send closed with the request context. :meth:`iter_bytes() <aioscraper.types.session.Response.iter_bytes>` and :meth:`read() <aioscraper.types.session.Response.read>` behave the same on either.
- **Cookies.** ``Response.cookies`` is a ``SimpleCookie`` on both; httpx's own cookie jar is converted.
- **URLs.** ``params`` extend the query the URL already carries on both backends, so ``?tag=old`` with ``params={"tag": "new"}`` is sent as ``?tag=old&tag=new``. On httpx they are merged into the URL before the request is built.

An injected client keeps its own timeout, SSL, proxy and redirect settings, so the second table no longer describes it, and neither does the redirect limit above. The per-request fields are applied to it as they are to any client, ``Request.timeout`` included.
