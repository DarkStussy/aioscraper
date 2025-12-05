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

   pip install "aioscraper[aiohttp]"   # recommended default
   # or
   pip install "aioscraper[httpx]"

At runtime ``aioscraper`` will use ``aiohttp`` when available, otherwise it falls back to ``httpx``.

Optional: install with ``uvloop`` (POSIX)
-----------------------------------------

``uvloop`` can speed up event loop operations on Linux/macOS:

.. code-block:: bash

   pip install "aioscraper[uvloop]"

If you plan to use ``--uvloop`` in the CLI, install this extra on supported platforms.

Developer extras
----------------
- Tests: ``pip install "aioscraper[test]"``
- Lint/format/type-check: ``pip install "aioscraper[dev]"``
- Combine extras as needed, e.g. ``pip install "aioscraper[aiohttp,httpx,test]"``

Next steps
----------
- Follow :doc:`quickstart` for your first scraper.
- See :doc:`cli` for running via the command line (including ``--uvloop``).
