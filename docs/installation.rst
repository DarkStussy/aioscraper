Installation Guide
==================

Requirements
------------
- Python 3.11+
- One HTTP backend: ``aiohttp`` (recommended), ``httpx`` or ``httpx2``
- POSIX for optional ``uvloop`` (not available on Windows)

Install with an HTTP backend
----------------------------
``aioscraper`` ships without an HTTP client. Pick one of the extras so requests work out of the box:

.. code-block:: bash

   # Option 1: Use aiohttp with speedups (recommended for most cases)
   pip install "aioscraper[aiohttp-speedups]"

   # Option 2: Use aiohttp without speedups (minimal dependencies)
   pip install "aioscraper[aiohttp]"

   # Option 3: Use httpx (if you prefer httpx ecosystem)
   pip install "aioscraper[httpx]"

   # Option 4: Use httpx2, the Pydantic-maintained fork of httpx
   pip install "aioscraper[httpx2]"

   # Option 5: Install several backends for flexibility
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
