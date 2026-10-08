# LogPulse local MVP — security and threat note

## Boundary and intended use

This is a local, single-user dashboard for **fictional or manually entered health metadata only**. It does not ingest logs/events, connect to a collector, discover sources, scan/probe systems, execute detections, or take response actions. Do not enter production SOC telemetry, confidential data, personal data, or customer content pending a separate security/privacy review. This is not deployed SaaS or a production monitoring service.

The trust boundary is one trusted workstation user, local browser, a loopback Python process, and local plaintext SQLite. There is no authentication, roles, tenant isolation, remote integration, or protection against other local processes/users. Localhost HTTP is not TLS. SQLite and WAL/SHM files are **not encrypted at rest**; restrictive file permissions are best-effort only.

## Implemented safeguards

- Bind is restricted to `127.0.0.1`; requests require the exact loopback Host.
- Writes require exact same-origin Origin, `Sec-Fetch-Site: same-origin`, and a random process-local token checked in constant time. No CORS allow-origin header is sent.
- Strict self-only CSP, security headers, no-store responses, and fixed static routes; no third-party scripts/styles/fonts or user-supplied URLs.
- File/body size, row count, fields, integer ranges, identifier format, enum values, string lengths, and timestamps are validated. SQL operations bind values.
- User/imported strings are rendered as text. Health reasons derive only from the metadata in the local database and the stated local thresholds.
- No network calls, source integrations, raw event storage, or remote control channel are present.

## Residual risks / assumptions

A local user/process can view or modify the database, fake timestamps/counts, or change threshold/mapping notes. Audit history is ordinary SQLite data, not tamper-proof. A “healthy” state means only that supplied values fit the implemented rule at display time; it does not prove a source, parser, detection, or visibility mapping is real or effective. Local host compromise, browser extensions, backups, and shared-computer users are outside this MVP's controls. System clock inaccuracies can affect freshness calculations.

## Data handling and removal

Only health metadata is stored at `data/workspace.sqlite3` (and SQLite journal sidecars); no event bodies are supported. The database is plaintext and should contain synthetic values only. **Reset to sample** clears previous local metadata/audit history and restores the fictional fixture with a reset marker. For full removal, stop the service and run `./reset.sh`, then verify the generated files are gone. Runtime data must not be committed.

This note is not a security assessment, compliance claim, or guarantee of production suitability.
