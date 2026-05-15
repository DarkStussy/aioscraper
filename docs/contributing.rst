Contributing
============

Thank you for considering contributing! Here is how to get set up and what we expect.

How to setup
------------

- Install `uv <https://docs.astral.sh/uv/>`_ (the project uses ``uv`` for dependency management and command execution).

- Clone the repo:

  .. code-block:: bash

     git clone https://github.com/darkstussy/aioscraper.git
     cd aioscraper

- Install Python interpreters used by the test matrix (uv will fetch them if missing):

  .. code-block:: bash

     uv python install 3.11 3.12 3.13 3.14

- Sync the environment with all extras and dev dependencies:

  .. code-block:: bash

     uv sync --extra aiohttp-speedups --extra httpx --extra uvloop

- Enable git hooks (we recommend ``prek``, a Rust alternative to ``pre-commit``; using ``pre-commit`` is fine if you prefer):

  .. code-block:: bash

     uv tool install prek
     prek install

Running tests
-------------

- Unit/integration tests:

  .. code-block:: bash

     uv run pytest

- Some HTTP integration tests spin up local aiohttp/httpx clients and may require network/socket permissions in your environment.

Style, linting, typing
----------------------

- Formatting and linting use `Ruff <https://docs.astral.sh/ruff/>`_ (configured in ``.ruff.toml``).
- Type checking uses `BasedPyright <https://docs.basedpyright.com/>`_ (configured in ``pyrightconfig.json``).
- Please format code and add tests for new behavior.
- Keep documentation in sync with code changes.

.. note::
   Install IDE extensions for better development experience:

   - `Ruff extension <https://docs.astral.sh/ruff/editors/setup/>`_
   - `BasedPyright extension <https://docs.basedpyright.com/latest/installation/ides/#vscode-vscodium>`_

Build documentation
-------------------

The project documentation is built with Sphinx. You may need ``make`` available on your system. Build the docs with:

.. code-block:: bash

   uv run --with-requirements docs/requirements.txt sphinx-build -M html docs docs/build -W

After a successful build, view the generated documentation by opening ``docs/build/html/index.html`` in your browser.

Submitting changes
------------------

- Open an issue first if you’re proposing a larger change.
- Keep commits focused and include a brief description of motivation and behavior.
