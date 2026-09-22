Installation Guide
==================

Requirements
------------
- Python 3.11+
- One HTTP backend: ``aiohttp`` (recommended), ``httpx`` or ``httpx2``
- POSIX for optional ``uvloop`` (not available on Windows)

Install with an HTTP backend
----------------------------
``aioscraper`` ships without an HTTP client, so install one of the extras - without it, no request can be sent:

.. code-block:: bash

   # aiohttp with its own speedups extra: aiodns for DNS resolution,
   # Brotli and backports.zstd for decoding those response encodings
   pip install "aioscraper[aiohttp-speedups]"

   # aiohttp with none of those
   pip install "aioscraper[aiohttp]"

   # httpx
   pip install "aioscraper[httpx]"

   # httpx2, the Pydantic-maintained fork of httpx
   pip install "aioscraper[httpx2]"

   # several at once, to choose between them per run
   pip install "aioscraper[aiohttp-speedups,httpx]"

At runtime ``aioscraper`` will use ``aiohttp`` when available, then ``httpx``, then ``httpx2``.

You can explicitly set the backend by setting the ``SESSION_HTTP_BACKEND`` environment variable to ``aiohttp``, ``httpx`` or ``httpx2``.

Backend differences
-------------------

httpx resolves proxies per transport and redirect limits per client, so these
:class:`~aioscraper.types.Request` fields cannot vary per request on that backend - or on
``httpx2``, which keeps its API - and raise
:class:`~aioscraper.exceptions.UnsupportedRequestOption`:

- ``proxy`` - set ``SessionConfig.proxy`` instead
- ``proxy_auth`` - embed the credentials in the ``SessionConfig.proxy`` URL
- ``proxy_headers`` - no equivalent
- ``max_redirects`` - fixed at the ``Request`` default for the whole session

Choose ``aiohttp`` if you need any of them per request. :doc:`backends` compares the three in full.

Optional: install with ``uvloop`` (POSIX)
-----------------------------------------

``uvloop`` can speed up event loop operations on Linux/macOS:

.. code-block:: bash

   pip install "aioscraper[uvloop]"

If you plan to use ``--uvloop`` in the CLI, install this extra on supported platforms.

Next steps
----------
- Follow :doc:`quickstart` for your first scraper.
- See :doc:`cli` for running via the command line (including ``--uvloop``).
