# TriageSignal local MVP

A **local-only, single-user** demonstration for reviewing fictional alert records, inspecting source-attributed evidence references, and saving human analyst notes/status. This is not deployed SaaS, a production SOC tool, or an incident-response console. The prior design proposal and static prototype remain separate and unchanged.

## Run locally

Requirements: Python 3.10 or newer; no third-party packages, build step, account, API key, or internet access is required.

```sh
cd projects/security-operations/TriageSignal/mvp
./run.sh
```

Open **http://127.0.0.1:8761/**. Keep the terminal open and press `Ctrl+C` to stop. `run.sh` explicitly binds to `127.0.0.1`; the server refuses non-loopback binds. For an alternate local port, run `python3 core.py --host 127.0.0.1 --port 9876` and use the printed address. Open this exact IP address (not a hostname) so Host/Origin checks match.

The first launch is empty. Choose **Load fictional sample** to add the invented records in `samples.json`; choose an alert to inspect its evidence and save an analyst note/status. JSON or CSV files may also be imported. Files are read in the browser and sent only to this local service. No alert enrichment or model call occurs.

## Import format and limits

- Maximum file size: **512 KiB**; **1–200** records per import; **200 alerts total** in the workspace; UTF-8 JSON or CSV only.
- JSON is an array of objects with exactly `id`, `source`, `severity`, `occurred_at`, `summary`, and optional `evidence`.
- `evidence` is an array of at most 20 objects, each with exactly `id`, `source`, `observed_at`, and `summary`.
- CSV headers must be exactly `id,source,severity,occurred_at,summary,evidence_refs`. `evidence_refs` is a pipe-separated list of fictional reference IDs; the app labels them as CSV references and preserves their source/time relationship to the alert.
- Alert/evidence IDs allow only letters, digits, dot, colon, underscore, and dash. Timestamps must be ISO 8601 with an explicit timezone. Severity is `informational`, `low`, `medium`, `high`, or `critical`.
- Analyst notes are limited to 4,000 characters. Duplicate IDs, unknown fields, invalid timestamps, malformed input, and over-limit files are rejected. The app stores imported text as data, not HTML.

All records, references, names, and values must be synthetic. Do not import production, confidential, customer, or personal SOC data pending a security review.

## What is implemented

- Local JSON/CSV alert import, strict allowlisted validation, and a source-cited evidence view.
- Analyst-authored note and status workflow (`new`, `in_review`, `reviewed`, `follow_up`) with local audit events.
- `reviewed` and `follow_up` require a non-empty human note plus at least one citation selected from the alert's own source record or its supplied evidence IDs; citations are validated and recorded with the workflow event.
- Fictional sample load and confirmed reset-to-sample action.
- Responsive keyboard-accessible UI, visible loading/empty/error states, focus treatment, and reduced-motion support.
- Python standard-library HTTP server and SQLite persistence using bound SQL parameters.

**Not implemented:** AI/model calls; live alert sources; SIEM/EDR/IdP/cloud connectors; arbitrary network lookups; login, roles, users, or tenant isolation; case/ticket write-back; endpoint/account changes; incident response; encryption-at-rest; SaaS deployment; or production retention/availability guarantees.

## Architecture and defaults
The browser UI source lives in the hidden `.local-ui/` directory. The local Python server maps that folder to its fixed `/static/` routes; the repository's existing root-branch Jekyll Pages build ignores dot-prefixed folders by default, so this does not publish the app UI or change Pages settings.


The browser UI is static local HTML/CSS/JavaScript; the Python `core.py` server exposes a small JSON API and `domain.py` validates workflow inputs and reads/writes the local SQLite database. The app makes no outbound network requests. It uses fixed static routes, accepts only the exact loopback Host and same-origin write requests with a per-process random token, applies a strict same-origin CSP and security headers, limits request/file sizes, and creates no user-selectable file paths. UI text is inserted with DOM `textContent`, not HTML parsing. This is a protective local demo boundary, not authentication or a security certification.

Defaults: host `127.0.0.1`; port `8761`; SQLite file `data/workspace.sqlite3`; import maximum `512 KiB`; maximum `200` alerts total; maximum `10,000` audit events; note maximum `4,000` characters. The `data/` directory and SQLite file are ignored by Git. File permissions are restricted best-effort on Unix, but the database is **plaintext and not encrypted at rest**. No login or tenant isolation is implemented; treat this as a single-user sandbox on a trusted workstation.

## Reset and wipe

- In the app, **Reset to sample** asks for confirmation, deletes local alerts, notes, and prior audit history, then restores the fictional fixture. A new `demo_reset` audit marker is written. This cannot be undone.
- To wipe all database files, stop the server (`Ctrl+C`) and run `./reset.sh`. It removes only `data/workspace.sqlite3` and its SQLite WAL/SHM sidecars. The next start creates an empty database. The source fixture is not deleted.

## Tests

Run offline, from this directory:

```sh
python3 -m unittest discover -s tests -v
```

Tests cover input validation and limits, CSV/JSON imports, evidence references, status/note/audit changes, parameterized handling of injection-like text, persistence, demo reset, request-size enforcement, exact local Host/Origin/token checks, and response security headers.
