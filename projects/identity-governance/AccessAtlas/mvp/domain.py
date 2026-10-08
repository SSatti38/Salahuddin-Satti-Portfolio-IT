"""AccessAtlas local review logic. The decision journal has no provider write path."""
from __future__ import annotations

import csv
import io
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 512 * 1024
MAX_ROWS = 200
MAX_WORKSPACE_RECORDS = 200
MAX_AUDIT_EVENTS = 10_000
MAX_DECISIONS = 1_000
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
ACCOUNT_STATES = {"active", "disabled", "pending"}
OUTCOMES = {"retain", "follow_up"}


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def text(value: Any, name: str, limit: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ApiError(f"{name} must be text.")
    value = value.strip()
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ApiError(f"{name} must contain valid UTF-8 text.") from exc
    if (not value and not allow_empty) or len(value) > limit or "\x00" in value:
        raise ApiError(f"{name} is empty or exceeds its allowed length.")
    return value


def ident(value: Any, name: str) -> str:
    value = text(value, name, 80)
    if not ID_RE.fullmatch(value):
        raise ApiError(f"{name} must use letters, digits, dot, colon, underscore, or dash.")
    return value


def stamp(value: Any, name: str, *, allow_empty: bool = False) -> str:
    value = text(value, name, 40, allow_empty=allow_empty)
    if allow_empty and not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApiError(f"{name} must be an ISO 8601 timestamp with timezone, or blank where optional.") from exc
    if dt.tzinfo is None:
        raise ApiError(f"{name} must include a timezone.")
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ApiError("Duplicate JSON object keys are not accepted.")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise ApiError("Non-finite JSON numbers are not accepted.")


def normalize_identity(item: Any) -> dict[str, str]:
    allowed = {"id", "display_name", "account_state", "last_sign_in", "entitlement", "source", "snapshot_at", "evidence"}
    required = allowed
    if not isinstance(item, dict) or set(item) != required:
        raise ApiError("Each identity must use exactly the documented allowlisted fields.")
    state = text(item["account_state"], "account_state", 20).lower()
    if state not in ACCOUNT_STATES:
        raise ApiError("account_state must be active, disabled, or pending.")
    return {
        "id": ident(item["id"], "identity reference"),
        "display_name": text(item["display_name"], "display_name", 120),
        "account_state": state,
        "last_sign_in": stamp(item["last_sign_in"], "last_sign_in", allow_empty=True),
        "entitlement": text(item["entitlement"], "entitlement", 160),
        "source": text(item["source"], "source", 120),
        "snapshot_at": stamp(item["snapshot_at"], "snapshot_at"),
        "evidence": text(item["evidence"], "evidence", 1_200),
    }


def parse_import(fmt: Any, content: Any) -> list[dict[str, str]]:
    if fmt not in {"json", "csv"}:
        raise ApiError("Choose JSON or CSV format.")
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ApiError("File must be UTF-8 text no larger than 512 KiB.", 413)
    try:
        if fmt == "json":
            rows = json.loads(content, object_pairs_hook=_pairs, parse_constant=_constant)
            if not isinstance(rows, list):
                raise ApiError("JSON import must be an array of identity objects.")
        else:
            reader = csv.DictReader(io.StringIO(content, newline=""), strict=True)
            expected = {"id", "display_name", "account_state", "last_sign_in", "entitlement", "source", "snapshot_at", "evidence"}
            if not reader.fieldnames or len(reader.fieldnames) != len(expected) or set(reader.fieldnames) != expected:
                raise ApiError("CSV must include exactly the documented identity snapshot columns.")
            rows = list(reader)
            if any(None in row or any(v is None for v in row.values()) for row in rows):
                raise ApiError("CSV rows have inconsistent column counts.")
    except (json.JSONDecodeError, csv.Error, RecursionError) as exc:
        raise ApiError("The file is malformed JSON or CSV.") from exc
    if not 1 <= len(rows) <= MAX_ROWS:
        raise ApiError("Import must contain between 1 and 200 identity records.")
    normalized = [normalize_identity(row) for row in rows]
    if len({row["id"] for row in normalized}) != len(normalized):
        raise ApiError("An import cannot contain duplicate identity references.")
    return normalized


class AppStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            try:
                self.path.parent.chmod(0o700)
            except OSError:
                pass
        self._initialize()
        if os.name == "posix":
            try:
                self.path.chmod(0o600)
            except OSError:
                pass

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=3)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        db.execute("PRAGMA busy_timeout = 3000")
        return db

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.execute("PRAGMA synchronous = FULL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS identities (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    account_state TEXT NOT NULL CHECK(account_state IN ('active','disabled','pending')),
                    last_sign_in TEXT NOT NULL,
                    entitlement TEXT NOT NULL,
                    source TEXT NOT NULL,
                    snapshot_at TEXT NOT NULL,
                    evidence TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    identity_id TEXT NOT NULL REFERENCES identities(id),
                    outcome TEXT NOT NULL CHECK(outcome IN ('retain','follow_up')),
                    reviewer TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS decisions_identity_idx ON decisions(identity_id,id DESC);
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    detail_json TEXT NOT NULL
                );
            """)

    def _audit(self, db: sqlite3.Connection, action: str, target: str, detail: dict[str, Any]) -> None:
        db.execute("INSERT INTO audit(action,target_id,created_at,detail_json) VALUES(?,?,?,?)", (action, target, utc_now(), json.dumps(detail, ensure_ascii=True, separators=(",", ":"))))

    def get_state(self) -> dict[str, Any]:
        with self._connect() as db:
            identities = [dict(row) for row in db.execute("""
                SELECT i.id,i.display_name,i.account_state,i.last_sign_in,i.entitlement,i.source,i.snapshot_at,i.evidence,
                  (SELECT d.outcome FROM decisions d WHERE d.identity_id=i.id ORDER BY d.id DESC LIMIT 1) AS latest_outcome,
                  (SELECT d.reviewer FROM decisions d WHERE d.identity_id=i.id ORDER BY d.id DESC LIMIT 1) AS latest_reviewer,
                  (SELECT d.created_at FROM decisions d WHERE d.identity_id=i.id ORDER BY d.id DESC LIMIT 1) AS latest_reviewed_at
                FROM identities i ORDER BY i.display_name,i.id LIMIT 250
            """).fetchall()]
            decisions = [dict(row) for row in db.execute("SELECT id,identity_id,outcome,reviewer,rationale,created_at FROM decisions ORDER BY id DESC LIMIT 1000").fetchall()]
            for identity in identities:
                identity["decisions"] = [decision for decision in decisions if decision["identity_id"] == identity["id"]]
            audit = [dict(row) for row in db.execute("SELECT id,action,target_id,created_at,detail_json FROM audit ORDER BY id DESC LIMIT 100").fetchall()]
            for row in audit:
                row["detail"] = json.loads(row.pop("detail_json"))
            return {"records": identities, "audit": audit}

    def _fixture(self) -> list[dict[str, str]]:
        rows = json.loads((Path(__file__).resolve().parent / "samples.json").read_text(encoding="utf-8"), object_pairs_hook=_pairs)
        return [normalize_identity(row) for row in rows]

    def _insert(self, db: sqlite3.Connection, rows: list[dict[str, str]]) -> None:
        for row in rows:
            db.execute("INSERT INTO identities(id,display_name,account_state,last_sign_in,entitlement,source,snapshot_at,evidence) VALUES(?,?,?,?,?,?,?,?)", tuple(row[k] for k in ("id", "display_name", "account_state", "last_sign_in", "entitlement", "source", "snapshot_at", "evidence")))

    def handle_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action in {"load_demo", "reset_demo"}:
            if payload:
                raise ApiError("This action does not accept fields.")
            fixture = self._fixture()
            with self._connect() as db:
                if action == "load_demo":
                    if db.execute("SELECT 1 FROM identities LIMIT 1").fetchone():
                        raise ApiError("Workspace already contains records. Choose Reset to sample to replace it.", 409)
                else:
                    db.execute("DELETE FROM decisions")
                    db.execute("DELETE FROM identities")
                    db.execute("DELETE FROM audit")
                if action == "load_demo" and db.execute("SELECT COUNT(*) FROM audit").fetchone()[0] >= MAX_AUDIT_EVENTS:
                    raise ApiError("Local audit event limit reached; reset the demo to continue.", 413)
                self._insert(db, fixture)
                self._audit(db, "fictional_demo_loaded" if action == "load_demo" else "demo_reset", "workspace", {"count": len(fixture), "fictional": True, "previous_history_cleared": action == "reset_demo"})
            message = f"Loaded {len(fixture)} fictional identities." if action == "load_demo" else "Local decisions and prior audit history were replaced with the fictional sample."
            return {"message": message}
        if action == "import":
            if set(payload) != {"format", "content"}:
                raise ApiError("Import requires format and content only.")
            rows = parse_import(payload["format"], payload["content"])
            try:
                with self._connect() as db:
                    count = db.execute("SELECT COUNT(*) FROM identities").fetchone()[0]
                    if count + len(rows) > MAX_WORKSPACE_RECORDS:
                        raise ApiError("Workspace is limited to 200 identities; reset the demo before adding more.", 413)
                    if db.execute("SELECT COUNT(*) FROM audit").fetchone()[0] >= MAX_AUDIT_EVENTS:
                        raise ApiError("Local audit event limit reached; reset the demo to continue.", 413)
                    self._insert(db, rows)
                    self._audit(db, "snapshot_imported", "workspace", {"count": len(rows), "format": payload["format"]})
            except sqlite3.IntegrityError as exc:
                raise ApiError("One or more identity references already exist; no rows were imported.", 409) from exc
            return {"message": f"Imported {len(rows)} fictional identity record(s)."}
        if action == "review":
            if set(payload) != {"id", "outcome", "reviewer", "rationale"}:
                raise ApiError("Review decision contains missing or unknown fields.")
            identity_id = ident(payload["id"], "identity reference")
            outcome = text(payload["outcome"], "outcome", 20)
            reviewer = text(payload["reviewer"], "reviewer label", 120)
            rationale = text(payload["rationale"], "rationale", 1_500)
            if outcome not in OUTCOMES:
                raise ApiError("Choose retain or follow_up.")
            with self._connect() as db:
                if db.execute("SELECT 1 FROM identities WHERE id=?", (identity_id,)).fetchone() is None:
                    raise ApiError("Identity was not found.", 404)
                if db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] >= MAX_DECISIONS:
                    raise ApiError("Local review history is limited to 1,000 decisions; reset the demo to continue.", 413)
                if db.execute("SELECT COUNT(*) FROM audit").fetchone()[0] >= MAX_AUDIT_EVENTS:
                    raise ApiError("Local audit event limit reached; reset the demo to continue.", 413)
                cursor = db.execute("INSERT INTO decisions(identity_id,outcome,reviewer,rationale,created_at) VALUES(?,?,?,?,?)", (identity_id, outcome, reviewer, rationale, utc_now()))
                decision_id = cursor.lastrowid
                self._audit(db, "review_decision_recorded", identity_id, {"decision_id": decision_id, "outcome": outcome, "reviewer": reviewer})
            return {"message": "Human review decision and rationale recorded locally."}
        raise ApiError("Unsupported action.", 404)
