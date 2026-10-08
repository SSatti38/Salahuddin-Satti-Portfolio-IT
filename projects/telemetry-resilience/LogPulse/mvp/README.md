# LogPulse local MVP

A **local-only, single-user** dashboard for fictional or manually entered telemetry-source health metadata. It shows freshness against an explicitly supplied cadence, parser status, rejected counts, backlog against a manually stated threshold, heartbeat, and a mapping reference with reviewer-supplied evidence. It stores no log events and never contacts or configures a source. This is not deployed SaaS, detection execution, or a production observability service; the original blueprint and static prototype remain separate and intact.

## Run locally

Requirements: Python 3.10 or newer; no third-party package, API key, account, build step, or internet access is needed.

```sh
cd projects/telemetry-resilience/LogPulse/mvp
./run.sh
```

Open **http://127.0.0.1:8763/**. Keep the terminal open and stop with `Ctrl+C`. The app binds only to `127.0.0.1` and rejects attempts to bind elsewhere. For another local port, run `python3 core.py --host 127.0.0.1 --port 9876` and open its printed address. Use the exact IP address, not a hostname.

The initial workspace is empty. Use the manual form to add or update health metadata, import a synthetic JSON/CSV file, or load the fictional sample. No collector, event feed, device, endpoint, or remote URL is contacted.

## Metadata schema and health logic

Each JSON array item or CSV row has exactly these fields: `id`, `name`, `owner`, `environment`, `expected_minutes`, `last_seen_at`, `parser_status`, `accepted_count`, `rejected_count`, `backlog_count`, `backlog_threshold`, `heartbeat_at`, `coverage_ref`, `coverage_notes`. Timestamps use ISO 8601 with an explicit timezone; last-seen/heartbeat may be blank in imported data, resulting in an unknown value. Environment is `Development`, `Test`, or `Demo`; parser state is `healthy`, `degraded`, or `failed`.

Limits: UTF-8 JSON/CSV only, **512 KiB**, **1–200 records per import** and **200 sources total** in the workspace, expected cadence 1–10,080 minutes, and counts/thresholds 0–10,000,000. IDs are limited to letters, digits, dot, colon, underscore, and dash. Unknown fields, duplicate source references, malformed rows, invalid times, and out-of-range values are rejected. Manual form values use the same server validation.

The displayed health is a transparent local derivation:

- `failed` when supplied parser state is failed;
- `stale` when the last-seen age exceeds `max(2 × expected_minutes, 5 minutes)`;
- `unknown` when no last-seen value is supplied (unless parser failure takes precedence);
- `degraded` when parser state is degraded, rejections are nonzero, or backlog exceeds its supplied threshold;
- otherwise `healthy`.

The UI explains freshness and threshold evidence. The algorithm does not verify a source, taxonomy, mapping, parser, detection, or the truth of supplied counts. “Healthy” is not proof of visibility, detection effectiveness, or security.

All names, timestamps, values, counts, mappings, and notes used must be synthetic. Do not enter production SOC telemetry, confidential data, or personal information pending a security review.

## What is implemented

- Synthetic/manual source-health metadata entry and JSON/CSV import with strict fields and bounds.
- Explainable freshness/parser/backlog states, threshold/mapping evidence display, and local audit events.
- Fictional sample load and confirmed reset-to-sample behavior.
- Accessible responsive UI, focus treatment, reduced motion, and visible empty/loading/error states.
- Standard-library Python HTTP app and parameterized SQLite persistence.

**Not implemented:** production log ingestion, SIEM/collector/forwarder connectors, source discovery, network probing/scanning, detection rules or execution, threat hunting, response or remediation actions, configuration changes to sources, authentication, roles, tenant isolation, SaaS deployment, encryption-at-rest, or production reliability/security claims.

## Architecture and defaults
The browser UI source lives in the hidden `.local-ui/` directory. The local Python server maps that folder to its fixed `/static/` routes; the repository's existing root-branch Jekyll Pages build ignores dot-prefixed folders by default, so this does not publish the app UI or change Pages settings.


Static local HTML/CSS/JavaScript uses a small Python JSON API and local SQLite. `domain.py` contains bounded metadata validation and explainable state derivation. The app makes no outbound network requests. The server binds to `127.0.0.1` only, serves an allowlist of fixed static paths, requires exact Host/Origin and a per-process random token on writes, caps request sizes, sets a strict CSP/security headers, and inserts imported text with DOM text APIs. These safeguards do not authenticate users or protect against other local processes/users.

Defaults: host `127.0.0.1`; port `8763`; SQLite path `data/workspace.sqlite3`; max file `512 KiB`; max `200` sources; max `10,000` audit events; state recalculated at display time against the local app clock. The database is **plaintext and not encrypted at rest**. Directory/file permissions are restricted best-effort only. There is no login or tenant isolation: single-user trusted-workstation sandbox only.

## Reset and wipe

- **Reset to sample** replaces local source metadata and previous audit history with the fictional fixtures, then records one `demo_reset` event. The UI asks for confirmation and the operation cannot be undone.
- For a full wipe, stop the server and run `./reset.sh`. It removes only the SQLite database and its WAL/SHM sidecars. The next run creates an empty workspace; `samples.json` remains available.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

The offline tests cover metadata bounds, JSON/CSV imports, freshness and health thresholds, manual add/update audit, persistence, parameterized handling of injection-like content, sample reset, local Host/Origin/token safeguards, request-size limits, and CSP/security headers.
