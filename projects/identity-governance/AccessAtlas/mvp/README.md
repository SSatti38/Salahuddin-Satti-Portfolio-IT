# AccessAtlas local MVP

A **local-only, single-user** review queue for fictional identity snapshots. A human inspects source/evidence context and records `retain` or `follow_up` with a reviewer label and rationale. Follow-up exists only in this local database; the app has no path to modify an account. This is not deployed SaaS or a production identity governance system. The existing blueprint and static prototype remain separate and intact.

## Run locally

Requirements: Python 3.10 or newer. The MVP uses only the standard library; it needs no third-party install, account, credential, build, or internet access.

```sh
cd projects/identity-governance/AccessAtlas/mvp
./run.sh
```

Open **http://127.0.0.1:8762/**. Keep the terminal open; `Ctrl+C` stops the service. The run script binds only to `127.0.0.1`; non-loopback host values are refused. To select another local port, run `python3 core.py --host 127.0.0.1 --port 9876` and open its printed address. Use the exact IP address, not a hostname.

The database begins empty. Choose **Load fictional sample** or import a synthetic JSON/CSV snapshot. Select an identity to inspect its source-reported snapshot and evidence, then explicitly choose an outcome, enter the reviewer label and rationale, and record the decision. Each decision is retained as a separate local history entry and referenced in the audit view.

## Snapshot schema and limits

- JSON array or CSV; UTF-8; maximum **512 KiB** and **1–200 identities per import**, with **200 identities total** in the workspace.
- Each record contains exactly: `id`, `display_name`, `account_state`, `last_sign_in`, `entitlement`, `source`, `snapshot_at`, `evidence`.
- `account_state` is `active`, `disabled`, or `pending`. `last_sign_in` may be blank; nonblank timestamps must be ISO 8601 with an explicit timezone. IDs allow only letters, digits, dot, colon, underscore, and dash.
- CSV headers must contain exactly the same eight field names. Unknown fields, duplicate references, malformed rows, over-limit files, and invalid values are rejected.
- Reviewer rationale is required and limited to 1,500 characters; reviewer label is limited to 120 characters.

Use fictional names and metadata only. Do not import production directories, real account/person identifiers, confidential HR/identity data, or customer information pending a security review.

## What is implemented

- Synthetic/manual snapshot import with an explicit allowlist and evidence field.
- Human review queue, explicit `retain` / `follow_up` choice, reviewer label, required rationale, and append-style decision history.
- Audit events for snapshot imports and reviewer choices; local sample load and confirmed reset.
- Responsive accessible interface, visible empty/loading/error states, keyboard focus, and reduced-motion support.
- Local Python standard-library HTTP app and SQLite persistence using bound SQL parameters.

**Not implemented:** OIDC/SSO/MFA, application users, assignment controls, login, roles, tenant isolation, Microsoft Graph/Okta/SCIM or any other connector, account provisioning/deprovisioning, access revocation, provider write-back, automated risk decisions, AI, SaaS deployment, encrypted exports, encryption-at-rest, or production retention/availability guarantees. A recorded `follow_up` is not a task sent to another system.

## Architecture and defaults
The browser UI source lives in the hidden `.local-ui/` directory. The local Python server maps that folder to its fixed `/static/` routes; the repository's existing root-branch Jekyll Pages build ignores dot-prefixed folders by default, so this does not publish the app UI or change Pages settings.


The static local HTML/CSS/JavaScript UI calls a small Python JSON API. `domain.py` validates snapshots and appends decisions/audit rows to SQLite; there is no external API client or outbound network request. Only fixed static paths are served. The server requires the configured loopback Host, exact same-origin writes, a fresh per-process request token, bounded body/file sizes, and uses a strict CSP and security headers. Imported strings are rendered as text, never parsed as HTML. These safeguards do not provide user authentication or isolate different local users.

Defaults: host `127.0.0.1`; port `8762`; database `data/workspace.sqlite3`; import max `512 KiB`; max `200` identity rows; maximum `1,000` decision-history entries and `10,000` audit events; rationale max `1,500` characters. SQLite is **plaintext and not encrypted at rest**; Unix file permissions are restricted best-effort only. No login or tenant isolation is implemented. Use only as a single-user sandbox on a trusted workstation.

## Reset and wipe

- **Reset to sample** replaces identities and decisions, clears prior audit history, restores the fictional fixture, and records a new `demo_reset` marker. The UI asks for confirmation; prior local review history cannot be recovered.
- To wipe the SQLite database and sidecars, stop the server and run `./reset.sh`. It removes only the generated database files; source samples remain, and a later start creates an empty database.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

The offline tests check input schema and bounds, JSON/CSV imports, human decision/audit history, persistence, injection-like text as inert data, demo reset, local Host/Origin/token enforcement, request-size limits, and security headers.
