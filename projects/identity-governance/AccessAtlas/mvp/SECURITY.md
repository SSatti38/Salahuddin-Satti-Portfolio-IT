# AccessAtlas local MVP — security and threat note

## Boundary and intended use

This is a local, single-user sandbox for **fictional identity metadata only**. It is not deployed SaaS, an identity provider, or a production access-review service. Do not import real account/person identifiers, production directory snapshots, confidential HR data, customer information, or other personal data pending a separate security/privacy review.

The trust boundary is one trusted workstation user, the local browser, one loopback Python process, and a plaintext SQLite database. There is no login, reviewer authentication, user/role system, assignment model, tenant isolation, OAuth, external connector, or protection from other local processes/users. The product cannot provision, disable, revoke, or otherwise change any account. Localhost HTTP is not TLS. SQLite and WAL/SHM files are **not encrypted at rest**; best-effort filesystem permissions are not encryption.

## Implemented safeguards

- Server binding accepts `127.0.0.1` only; exact loopback Host and exact same-origin POST Origin are required.
- State-changing requests also require `Sec-Fetch-Site: same-origin` and an unpredictable per-process token checked in constant time. No CORS allow-origin header is sent.
- Strict self-only CSP and security headers; fixed static file routes; no user-controlled path or URL fetching; no external scripts/styles/fonts.
- Snapshot imports are limited to UTF-8 JSON/CSV, 512 KiB, 200 records, exact field allowlists, bounded strings, constrained IDs and timestamps, and unique references.
- Reviewer outcomes are enumerated; rationale is required and bounded. SQL values use bound parameters; untrusted display values use text-only DOM operations.
- No provider write path or external network client exists.

## Residual risks / assumptions

Anyone able to use the local browser or read the database may view/alter data. A local token/origin check is not authentication. SQLite decision/audit rows are append-style during ordinary application use but can be edited by someone with filesystem access; they are not immutable, cryptographically signed, or independently witnessed. Imported identity/source evidence is not verified against a provider. Incorrect or misleading fictional values may create a false impression; decisions still require human judgment. Local compromise, backups, browser extensions, and shared workstations are outside this MVP's controls.

## Data handling and removal

The database is stored at `data/workspace.sqlite3` with SQLite sidecars. Values are plaintext, persist locally, and should remain fictional. **Reset to sample** deletes prior decisions and audit history, restores the built-in synthetic snapshot, and adds a reset marker. For a full wipe, stop the app and run `./reset.sh`; confirm the database and sidecars are absent. Keep runtime files out of Git.

This is a bounded implementation note, not a security review, compliance attestation, or production-readiness claim.
