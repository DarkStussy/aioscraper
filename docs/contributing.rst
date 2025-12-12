Contributing
============

Thank you for considering contributing! Here is how to get set up and what we expect.

How to setup
------------

- Install all needed python interpreters:

  - CPython 3.11
  - CPython 3.12
  - CPython 3.13
  - CPython 3.14

- Clone the repo:

  .. code-block:: bash

     git clone https://github.com/darkstussy/aioscraper.git
     cd aioscraper

- Create a virtualenv and install all extras:

  .. code-block:: bash

     python3 -m venv .venv
     source .venv/bin/activate
     pip install -e ".[aiohttp,httpx,uvloop]"
     pip install -r requirements_dev.txt

- Enable git hooks (we recommend ``prek``, a Rust alternative to ``pre-commit``; using ``pre-commit`` is fine if you prefer):

  .. code-block:: bash

     pip install prek
     prek install

Running tests
-------------

- Unit/integration tests:

  .. code-block:: bash

     pytest

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

The project documentation is built with Sphinx. You may need ``make`` available on your system. Start by installing the required dependencies:

.. code-block:: bash

   pip install -r docs/requirements.txt
   sphinx-build -M html docs docs/build -W

After a successful build, view the generated documentation by opening ``docs/build/html/index.html`` in your browser.

Submitting changes
------------------

- Open an issue first if you’re proposing a larger change.
- Keep commits focused and include a brief description of motivation and behavior.
