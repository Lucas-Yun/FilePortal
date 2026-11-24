# Security Policy

FilePortal is a self-hosted file service. Security reports are welcome, and good-faith research is appreciated. Please report privately and do not include real credentials, private file paths, personal data, or live production data in a public issue.

## Supported versions

Security fixes are applied to the latest published release. Older builds may receive best-effort fixes only.

| Version | Supported |
| --- | --- |
| Latest `v1.x` release | Yes |
| Older releases | Best effort |
| Unreleased forks or modified builds | No guarantee |

When reporting, please state the edition: source edition, Windows portable EXE, or Linux package.

## Reporting a vulnerability

**Preferred channel:** open a private report through GitHub Security Advisories:

<https://github.com/Lucas-Yun/FilePortal/security/advisories/new>

If private reporting is temporarily unavailable, open a minimal public issue **without exploit details** and ask the maintainer to establish a private channel. Do not paste secrets, tokens, session cookies, personal file names, or customer data into any issue.

Please include:

- affected version, release tag, and edition;
- operating system, Python version, and whether a reverse proxy/TLS is in use;
- a short description of the issue and the security property affected;
- reproduction steps or a minimal proof of concept;
- impact assessment and any suggested fix;
- whether you intend to disclose publicly, and your preferred timeline.

Do not test against systems you do not own or have explicit permission to test. Do not use real user accounts, production credentials, or third-party data.

## What to expect

This is a small community-maintained project, so response times are best effort rather than a contractual SLA. The maintainer will aim to:

1. acknowledge a complete report within 5 business days;
2. confirm scope and severity, and request missing details if needed;
3. prepare and test a fix, then coordinate a release and advisory;
4. credit the reporter unless anonymity is requested.

Please allow reasonable time for triage and remediation before public disclosure. A coordinated disclosure target of up to 90 days is normally appropriate; a shorter window may be agreed when a fix is ready or active exploitation is suspected. Reports containing personal data will be handled as confidential.

## Safe harbor

Good-faith security research conducted under this policy is welcome. The project will not pursue legal action or ask a platform to penalize research that:

- stays within accounts and systems the researcher owns or is authorized to test;
- avoids privacy violations, data destruction, service disruption, and persistence beyond what is necessary to demonstrate the issue;
- reports the issue privately and gives the maintainer a reasonable opportunity to fix it;
- does not extort, disclose, or sell the vulnerability.

This safe-harbor statement does not override applicable law, third-party terms, or authorization requirements.

## Security model and boundaries

FilePortal is a lightweight self-hosted file service, not a hardened enterprise storage platform. Its security depends on correct deployment, network controls, and configuration.

Recommended baseline:

- Change the default `Admin` password before exposing the service.
- Do not expose the service directly to the public internet over plain HTTP.
- Put a reverse proxy with TLS, authentication, rate limiting, and access control in front of public deployments.
- Do not project an entire disk, system directory, or user home directory.
- Grant `delete` and `rename` only to trusted users.
- Keep `config.ini`, `data/accounts.json`, `data/.session_secret`, TLS private keys, and logs out of source control.
- Back up `data/` and `config.ini` regularly; the recycle bin is not a backup.
- Run the service as an unprivileged account and restrict filesystem permissions to the projected directory.
- Review registrations, login rules, blocked paths, and online sessions regularly.

This repository intentionally ships with placeholder passwords and empty contact fields. Packaged editions should contain only the initial `Admin` account, no production rules, no real user lists, and no personal contact information.

## Built-in protections

- Real-path checks for traversal and symlink escape.
- Hidden/blocked path enforcement for direct URLs, listing, search, and ZIP packaging.
- Signed, expiring download tokens bound to the current rule fingerprint.
- Session cookies with `HttpOnly`, `SameSite=Lax`, HMAC signature, and expiration.
- Same-origin checks for POST requests from modern browsers.
- CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, and `Permissions-Policy` on HTML responses.
- Upload filename sanitization and Windows reserved-name handling.
- Login failure lockout, global rate limiting, and failure delay.
- Input validation for paths, ranges, filenames, and administrative actions.

These protections reduce common risks but do not replace network-level controls, backups, monitoring, or a hardened operating system.

## Supply chain and build integrity

- Runtime code uses the Python standard library; third-party runtime dependencies are intentionally avoided.
- Windows builds are produced by the GitHub Actions workflow from the reviewed source archive.
- Release assets include SHA-256 checksums next to each download.
- Build logs and artifacts are public; reproducible-build differences may still occur because of toolchain and runner versions.
- CodeQL runs on pushes, pull requests, and a weekly schedule to catch common Python security issues.
- Dependabot keeps GitHub Actions versions current; dependency updates still require human review.
- Do not trust binaries from unofficial mirrors. Download only from the official Releases page.

## Out of scope

The following are generally not treated as vulnerabilities by themselves:

- service unavailability caused by deliberately oversized uploads beyond configured limits;
- data loss caused by deleting files or emptying the recycle bin;
- misconfiguration that exposes a sensitive directory;
- missing code signing or SmartScreen warnings on unsigned Windows builds;
- issues requiring physical access to the server or an already-compromised administrator account;
- self-XSS or social engineering without a concrete security impact;
- reports that only demonstrate a missing header without explaining a realistic exploit path;
- vulnerabilities in third-party browsers, reverse proxies, or operating systems that are not caused by FilePortal code.

## Contact

Use the private advisory link above for security matters. For non-sensitive questions, use the repository issue tracker and the guidance in [SUPPORT.md](SUPPORT.md). Please do not send secrets by email or in a public issue.
