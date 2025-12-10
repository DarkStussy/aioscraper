Installation Guide
==================

Requirements
------------
- Python 3.11+
- One HTTP backend: ``aiohttp`` (recommended) or ``httpx``
- POSIX for optional ``uvloop`` (not available on Windows)

Install with an HTTP backend
----------------------------
``aioscraper`` ships without an HTTP client. Pick one of the extras so requests work out of the box:

.. code-block:: bash

   # Option 1: Use aiohttp (recommended for most cases)
   pip install "aioscraper[aiohttp]"

   # Option 2: Use httpx (if you prefer httpx ecosystem)
   pip install "aioscraper[httpx]"

   # Option 3: Install both backends for flexibility
   pip install "aioscraper[aiohttp,httpx]"

At runtime ``aioscraper`` will use ``aiohttp`` when available, otherwise it falls back to ``httpx``.

You can explicitly set the backend by setting the ``SESSION_HTTP_BACKEND`` environment variable to ``aiohttp`` or ``httpx``.

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
