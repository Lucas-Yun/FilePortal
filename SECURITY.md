# Security Policy

## Supported versions

Security fixes are applied to the latest release. Older builds may not receive updates.

| Version | Supported |
| --- | --- |
| Latest `v1.x` release | Yes |
| Older releases | Best effort |

## Reporting a vulnerability

Please **do not** open a public issue with exploit details, credentials, private file paths, or personal data.

Report privately through GitHub's **Security → Report a vulnerability** flow for this repository, or contact the maintainer through the GitHub profile linked in the repository.

Include:

- affected version and edition (source / portable / Linux);
- operating system and Python version;
- a short description of the issue;
- reproduction steps or a minimal proof of concept;
- impact and any suggested fix.

Please allow reasonable time for triage and a fix before public disclosure. Reports that include personal data will be handled as confidential.

## Security model and boundaries

FilePortal is a lightweight self-hosted file service, not a hardened enterprise storage platform. Its security depends on correct deployment and configuration.

Recommended baseline:

- Change the default `Admin` password before exposing the service.
- Do not expose the service directly to the public internet over plain HTTP.
- Put a reverse proxy with TLS, authentication, rate limiting, and access control in front of public deployments.
- Do not project an entire disk, system directory, or user home directory.
- Grant `delete` and `rename` only to trusted users.
- Keep `config.ini`, `data/accounts.json`, `data/.session_secret`, TLS private keys, and logs out of source control.
- Back up `data/` and `config.ini` regularly; the recycle bin is not a backup.

## Built-in protections

- Real-path checks for traversal and symlink escape.
- Hidden/blocked path enforcement for direct URLs, listing, search, and ZIP packaging.
- Signed, expiring download tokens bound to the current rule fingerprint.
- Session cookies with `HttpOnly`, `SameSite=Lax`, HMAC signature, and expiration.
- Same-origin checks for POST requests from modern browsers.
- CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `Permissions-Policy` on HTML responses.
- Upload filename sanitization and Windows reserved-name handling.
- Login failure lockout, global rate limiting, and failure delay.

These protections reduce common risks but do not replace network-level controls, backups, or operational monitoring.

## Out of scope

The following are generally not treated as vulnerabilities by themselves:

- service unavailability caused by deliberately oversized uploads beyond configured limits;
- data loss caused by deleting files or emptying the recycle bin;
- misconfiguration that exposes a sensitive directory;
- missing code signing or SmartScreen warnings on unsigned Windows builds;
- issues requiring physical access to the server or an already-compromised administrator account.
