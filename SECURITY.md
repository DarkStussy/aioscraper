# Security Policy

## Supported versions

aioscraper is still pre-1.0. Security fixes are released for the latest version only.

If you found a problem in an older version, please check whether it also affects the
latest release, if practical.

| Version        | Supported |
| -------------- | --------- |
| Latest release | yes       |
| Older releases | no        |

## Reporting a vulnerability

Please report suspected security vulnerabilities privately through
[GitHub Security Advisories](https://github.com/darkstussy/aioscraper/security/advisories/new).
Do not include vulnerability details in a public issue.

A useful report includes:

- the affected aioscraper version;
- the HTTP backend and its version;
- the Python version;
- the expected security impact;
- steps to reproduce the problem or a minimal reproducer.

Please remove real credentials and other sensitive data from the report.

We aim to acknowledge reports within 7 days and will keep you informed while we
investigate. Confirmed vulnerabilities will be fixed in a new release and documented
in the changelog. A GitHub advisory will be published when appropriate.

## Scope

aioscraper makes outbound HTTP requests to servers it does not control. Relevant
security issues include, for example:

- credentials or sensitive headers being sent to an unintended host;
- configured proxy or other security-sensitive request settings being bypassed;
- excessive CPU or memory use triggered by a remote response.

A failed response is read into the `HTTPException` message, up to
`session.max_error_body_size` (64 KiB by default), and that message reaches your logs.
Where an endpoint echoes credentials or personal data in an error body, set the limit
to `0` to skip reading it. This is a documented trade-off, not a vulnerability.

Bugs without a security impact should be reported through the public issue tracker.

Vulnerabilities entirely within `aiohttp`, `httpx` or `httpx2` should normally be reported
upstream. If an upstream behavior makes aioscraper unsafe or requires mitigation in
aioscraper itself, please report it to us as well.
