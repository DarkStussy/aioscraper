Compatibility policy
====================

Public API is exactly three things: the names listed in :doc:`api`, the ``SESSION_*``/``SCHEDULER_*``/``EXECUTION_*``/``PIPELINE_*`` environment variables, and the CLI flags and exit codes in :doc:`cli`. Everything else may change in any release, whether or not it is importable - a name absent from :doc:`api` is internal even when nothing marks it as such.

The project is pre-1.0, so a ``0.x`` release may change or remove public API without a deprecation period. Every such change is listed in the changelog under **BREAKING**, with what replaces it.

From 1.0 the versioning is `SemVer <https://semver.org/>`_, and a public API scheduled for removal is deprecated first: it keeps working and emits a ``DeprecationWarning`` naming its replacement for at least two minor releases, and is removed no earlier than the next major.

Supported Python versions are the ones in ``project.requires-python``; one is dropped no earlier than its `end of life <https://devguide.python.org/versions/>`_. The ``aiohttp`` and ``httpx`` floors in the extras may be raised in a minor release, including to clear a vulnerability in the client.
