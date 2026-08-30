# Security Policy

## Reporting

Do not open a public issue for a vulnerability. Use the private vulnerability
reporting or private maintainer-contact mechanism provided by the repository
host. If no private channel is available in a redistributed copy, contact the
distributor privately before publishing details.

Include the affected version, reproduction steps, impact, and any proposed
mitigation. Please avoid including real personal data or credentials.

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | Yes |

## In scope

- bypassing consent, purpose, cohort-size, approval, or guardrail enforcement;
- making sensitive or direct identifiers influence ranking;
- cross-request event linkage or idempotency failures;
- audit-chain mutation that is not detected;
- SQL injection, path traversal, cross-site scripting, or unsafe static assets;
- denial of service through unbounded API input;
- secrets or private data committed to the package.

## Security boundaries

The local demo has no authentication or organizational authorization layer and
must not be exposed to an untrusted network. SQLite state, same-process audit
hashing, browser confirmation dialogs, and local operator names are evaluation
mechanisms—not production identity, tamper-proof storage, or non-repudiation.
See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) and
[docs/ETHICS.md](docs/ETHICS.md) before adapting the project.
