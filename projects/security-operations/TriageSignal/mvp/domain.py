"""TriageSignal's local-only domain logic. No network, model, or source integrations."""
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
MAX_TEXT = 4_000
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
SEVERITIES = {"informational", "low", "medium", "high", "critical"}
STATUSES = {"new", "in_review", "reviewed", "follow_up"}


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def bounded_text(value: Any, name: str, max_length: int, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ApiError(f"{name} must be text.")
    value = value.strip()
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ApiError(f"{name} must contain valid UTF-8 text.") from exc
    if (not value and not allow_empty) or len(value) > max_length or "\x00" in value:
        raise ApiError(f"{name} is empty or exceeds its allowed length.")
    return value


def identifier(value: Any, name: str) -> str:
    value = bounded_text(value, name, 80)
    if not ID_RE.fullmatch(value):
        raise ApiError(f"{name} must use letters, digits, dot, colon, underscore, or dash.")
    return value


def timestamp(value: Any, name: str) -> str:
    value = bounded_text(value, name, 40)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApiError(f"{name} must be an ISO 8601 timestamp with a timezone.") from exc
    if parsed.tzinfo is None:
        raise ApiError(f"{name} must include a timezone.")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _pairs_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise ApiError("Duplicate JSON object keys are not accepted.")
        obj[key] = value
    return obj


def _json_constant(_: str) -> None:
    raise ApiError("Non-finite JSON numbers are not accepted.")


def _normalize_evidence(value: Any, alert_source: str, observed_at: str) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 20:
        raise ApiError("evidence must be an array of at most 20 references.")
    normalized = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {"id", "source", "observed_at", "summary"}:
            raise ApiError("Each evidence reference must contain only id, source, observed_at, and summary.")
        normalized.append({
            "id": identifier(item["id"], "evidence id"),
            "source": bounded_text(item["source"], "evidence source", 120),
            "observed_at": timestamp(item["observed_at"], "evidence observed_at"),
            "summary": bounded_text(item["summary"], "evidence summary", 500),
        })
    return normalized


def normalize_alert(item: Any) -> dict[str, Any]:
    allowed = {"id", "source", "severity", "occurred_at", "summary", "evidence"}
    if not isinstance(item, dict) or set(item) - allowed or not {"id", "source", "severity", "occurred_at", "summary"}.issubset(item):
        raise ApiError("Each alert must use the documented allowlisted fields.")
    severity = bounded_text(item["severity"], "severity", 20).lower()
    if severity not in SEVERITIES:
        raise ApiError("severity must be informational, low, medium, high, or critical.")
    occurred_at = timestamp(item["occurred_at"], "occurred_at")
    return {
        "id": identifier(item["id"], "alert id"),
        "source": bounded_text(item["source"], "source", 120),
        "severity": severity,
        "occurred_at": occurred_at,
        "summary": bounded_text(item["summary"], "summary", 2_400),
        "evidence": _normalize_evidence(item.get("evidence", []), item["source"], occurred_at),
    }


def parse_alert_import(fmt: Any, content: Any) -> list[dict[str, Any]]:
    if fmt not in {"json", "csv"}:
        raise ApiError("Choose JSON or CSV format.")
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ApiError("File must be UTF-8 text no larger than 512 KiB.", 413)
    try:
        if fmt == "json":
            raw = json.loads(content, object_pairs_hook=_pairs_no_duplicates, parse_constant=_json_constant)
            if not isinstance(raw, list):
                raise ApiError("JSON import must be an array of alert objects.")
            items = raw
        else:
            reader = csv.DictReader(io.StringIO(content, newline=""), strict=True)
            expected = {"id", "source", "severity", "occurred_at", "summary", "evidence_refs"}
            if not reader.fieldnames or len(reader.fieldnames) != len(expected) or set(reader.fieldnames) != expected:
                raise ApiError("CSV headers must be exactly: id,source,severity,occurred_at,summary,evidence_refs.")
            items = []
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ApiError("CSV rows have inconsistent column counts.")
                evidence_text = row.pop("evidence_refs").strip()
                refs = []
                if evidence_text:
                    refs = [{"id": ref.strip(), "source": row["source"], "observed_at": row["occurred_at"], "summary": "Fictional CSV evidence reference."} for ref in evidence_text.split("|") if ref.strip()]
                row["evidence"] = refs
                items.append(row)
                if len(items) > MAX_ROWS:
                    raise ApiError("Import is limited to 200 alerts.", 413)
    except (json.JSONDecodeError, csv.Error, RecursionError) as exc:
        raise ApiError("The file is malformed JSON or CSV.") from exc
    if not 1 <= len(items) <= MAX_ROWS:
        raise ApiError("Import must contain between 1 and 200 alerts.")
    normalized = [normalize_alert(item) for item in items]
    if len({item["id"] for item in normalized}) != len(normalized):
        raise ApiError("An import cannot contain duplicate alert IDs.")
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
        conn = sqlite3.connect(self.path, timeout=3)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 3000")
        return conn

    def _initialize(self) -> None:
        with self._connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.execute("PRAGMA synchronous = FULL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    evidence_json TEXT NOT NULL,
                    citations_json TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('new','in_review','reviewed','follow_up')),
                    analyst_note TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
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
            alerts = [dict(row) for row in db.execute("SELECT id,source,severity,occurred_at,summary,evidence_json,citations_json,status,analyst_note,updated_at FROM alerts ORDER BY occurred_at DESC,id LIMIT 250").fetchall()]
            for row in alerts:
                row["evidence"] = json.loads(row.pop("evidence_json"))
                row["citations"] = json.loads(row.pop("citations_json"))
            audit = [dict(row) for row in db.execute("SELECT id,action,target_id,created_at,detail_json FROM audit ORDER BY id DESC LIMIT 100").fetchall()]
            for row in audit:
                row["detail"] = json.loads(row.pop("detail_json"))
            return {"records": alerts, "audit": audit}

    def _insert_alerts(self, db: sqlite3.Connection, alerts: list[dict[str, Any]]) -> None:
        now = utc_now()
        for alert in alerts:
            db.execute("INSERT INTO alerts(id,source,severity,occurred_at,summary,evidence_json,citations_json,status,analyst_note,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)", (alert["id"], alert["source"], alert["severity"], alert["occurred_at"], alert["summary"], json.dumps(alert["evidence"], ensure_ascii=True), "[]", "new", "", now))

    def _fixture(self) -> list[dict[str, Any]]:
        fixture = json.loads((Path(__file__).resolve().parent / "samples.json").read_text(encoding="utf-8"), object_pairs_hook=_pairs_no_duplicates)
        return [normalize_alert(item) for item in fixture]

    def _ensure_empty(self, db: sqlite3.Connection) -> None:
        if db.execute("SELECT 1 FROM alerts LIMIT 1").fetchone():
            raise ApiError("Workspace already contains records. Choose Reset to sample to replace it, or use a new database.", 409)

    def handle_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "load_demo":
            if payload:
                raise ApiError("This action does not accept fields.")
            fixture = self._fixture()
            try:
                with self._connect() as db:
                    self._ensure_empty(db)
                    if db.execute("SELECT COUNT(*) FROM audit").fetchone()[0] >= MAX_AUDIT_EVENTS:
                        raise ApiError("Local audit event limit reached; reset the demo to continue.", 413)
                    self._insert_alerts(db, fixture)
                    self._audit(db, "fictional_demo_loaded", "workspace", {"count": len(fixture), "fictional": True})
            except sqlite3.IntegrityError as exc:
                raise ApiError("Fictional sample IDs conflict with existing records.", 409) from exc
            return {"message": f"Loaded {len(fixture)} fictional alerts."}
        if action == "reset_demo":
            if payload:
                raise ApiError("This action does not accept fields.")
            fixture = self._fixture()
            with self._connect() as db:
                db.execute("DELETE FROM alerts")
                db.execute("DELETE FROM audit")
                self._insert_alerts(db, fixture)
                self._audit(db, "demo_reset", "workspace", {"count": len(fixture), "previous_history_cleared": True, "fictional": True})
            return {"message": "Local records, notes, and prior audit history were replaced with the fictional sample."}
        if action == "import":
            if set(payload) != {"format", "content"}:
                raise ApiError("Import requires format and content only.")
            alerts = parse_alert_import(payload["format"], payload["content"])
            try:
                with self._connect() as db:
                    count = db.execute("SELECT COUNT(*) FROM alerts").fetchone()[0]
                    if count + len(alerts) > MAX_WORKSPACE_RECORDS:
                        raise ApiError("Workspace is limited to 200 alerts; reset the demo before adding more.", 413)
                    if db.execute("SELECT COUNT(*) FROM audit").fetchone()[0] >= MAX_AUDIT_EVENTS:
                        raise ApiError("Local audit event limit reached; reset the demo to continue.", 413)
                    self._insert_alerts(db, alerts)
                    self._audit(db, "alerts_imported", "workspace", {"count": len(alerts), "format": payload["format"]})
            except sqlite3.IntegrityError as exc:
                raise ApiError("One or more alert IDs already exist; no rows were imported.", 409) from exc
            return {"message": f"Imported {len(alerts)} fictional alert record(s)."}
        if action == "save_alert":
            if set(payload) != {"id", "status", "analyst_note", "citations"}:
                raise ApiError("Review update contains missing or unknown fields.")
            alert_id = identifier(payload["id"], "alert id")
            status = bounded_text(payload["status"], "status", 20)
            note = bounded_text(payload["analyst_note"], "analyst note", MAX_TEXT, allow_empty=True)
            raw_citations = payload["citations"]
            if not isinstance(raw_citations, list) or len(raw_citations) > 21:
                raise ApiError("Choose at most 21 valid source/evidence citations.")
            citations = [bounded_text(value, "citation reference", 90) for value in raw_citations]
            if len(set(citations)) != len(citations):
                raise ApiError("Citation references cannot be duplicated.")
            if status not in STATUSES:
                raise ApiError("Choose a supported review status.")
            with self._connect() as db:
                row = db.execute("SELECT status,evidence_json FROM alerts WHERE id=?", (alert_id,)).fetchone()
                if row is None:
                    raise ApiError("Alert was not found.", 404)
                allowed_citations = {f"alert:{alert_id}"} | {item["id"] for item in json.loads(row["evidence_json"])}
                if not set(citations).issubset(allowed_citations):
                    raise ApiError("Every citation must reference this alert or one of its supplied evidence records.")
                if status in {"reviewed", "follow_up"} and (not note or not citations):
                    raise ApiError("Reviewed and follow-up statuses require a human note and at least one source/evidence citation.")
                if db.execute("SELECT COUNT(*) FROM audit").fetchone()[0] >= MAX_AUDIT_EVENTS:
                    raise ApiError("Local audit event limit reached; reset the demo to continue.", 413)
                db.execute("UPDATE alerts SET status=?,analyst_note=?,citations_json=?,updated_at=? WHERE id=?", (status, note, json.dumps(citations, ensure_ascii=True), utc_now(), alert_id))
                self._audit(db, "alert_review_updated", alert_id, {"from": row["status"], "to": status, "note_length": len(note), "citations": citations})
            return {"message": "Analyst status and note saved locally."}
        raise ApiError("Unsupported action.", 404)
