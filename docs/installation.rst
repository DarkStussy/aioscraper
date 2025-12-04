Installation Guide
==================

Requirements
------------
- Python 3.11+
- POSIX for optional ``uvloop`` (not available on Windows)

Install the core package
------------------------

.. code-block:: bash

   pip install aioscraper

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

Next steps
----------
- Follow :doc:`quickstart` for your first scraper.
- See :doc:`cli` for running via the command line (including ``--uvloop``).
