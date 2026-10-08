# TriageSignal local MVP — security and threat note

## Boundary and intended use

This is a local, single-user sandbox for **fictional data only**. It is not a deployed service, security product, incident-response tool, or certified/production-ready application. Do not import production/confidential SOC data or personal/customer records until a separate security and privacy review approves the use case.

The trust boundary is one trusted workstation user, the local browser, the loopback Python process, and a plaintext SQLite file. There is no login, role model, tenant isolation, remote service, external connection, or protection against another process/user with local access. Localhost HTTP is not TLS. SQLite and its WAL/SHM files are **not encrypted at rest**; file mode restrictions are best-effort and do not constitute encryption.

## Implemented safeguards

- Bind is fixed to IPv4 loopback (`127.0.0.1`); attempts to select another bind host fail.
- Exact loopback `Host` is required, and POST actions require exact same-origin `Origin`, browser `Sec-Fetch-Site: same-origin`, and an unpredictable process-local token compared in constant time.
- No CORS allowlist is emitted. The server uses a strict self-only Content Security Policy, `nosniff`, clickjacking/referrer/permissions controls, no-store caching, fixed static routes, and closes responses.
- Request bodies are bounded; imports have a 512 KiB/200-row cap, field allowlists and lengths, timezone-aware timestamp validation, and duplicate-ID rejection.
- SQLite statements bind values; imported strings render as text (`textContent`/form values), not HTML. No imported path, URL, SQL fragment, or executable expression is accepted.
- No AI, source connector, response action, or outbound network feature exists in this MVP.

## Residual risks / assumptions

A malicious local process, browser extension, compromised workstation, user with filesystem access, or unsafe browser add-on may read or alter records. The per-process token and origin checks mitigate cross-site browser writes but are not user authentication. A local user can edit SQLite directly; audit rows are ordinary local data, not tamper-proof evidence. A forged or misleading synthetic import may still mislead a human; provenance values are user-supplied and not externally verified. Backups/copies are outside the app's control. Shared computers are not an appropriate use without separate protections.

## Data handling and removal

Data lives under this folder at `data/workspace.sqlite3` plus SQLite journal sidecars. It persists until reset or manual wipe, is not encrypted, and should contain fictional examples only. The UI reset action clears prior alerts, notes, and audit history before loading the built-in sample. For complete removal, stop the service and execute `./reset.sh`; verify the generated database files are gone. Do not commit SQLite files.

This note records design boundaries only; it is not a security assessment, compliance claim, or guarantee that vulnerabilities are absent.
