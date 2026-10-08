"""LogPulse local health metadata logic. No event ingestion, probing, or response path."""
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
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,79}$")
PARSER_STATES = {"healthy", "degraded", "failed"}
ENVIRONMENTS = {"Development", "Test", "Demo"}
FIELDS = ("id", "name", "owner", "environment", "expected_minutes", "last_seen_at", "parser_status", "accepted_count", "rejected_count", "backlog_count", "backlog_threshold", "heartbeat_at", "coverage_ref", "coverage_notes")


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


def number(value: Any, name: str, low: int, high: int) -> int:
    if isinstance(value, bool):
        raise ApiError(f"{name} must be an integer.")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str) and value.isdigit():
        parsed = int(value)
    else:
        raise ApiError(f"{name} must be an integer.")
    if not low <= parsed <= high:
        raise ApiError(f"{name} must be between {low} and {high}.")
    return parsed


def stamp(value: Any, name: str, *, allow_empty: bool = False) -> str:
    value = text(value, name, 40, allow_empty=allow_empty)
    if allow_empty and not value:
        return ""
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ApiError(f"{name} must be an ISO 8601 timestamp with timezone.") from exc
    if dt.tzinfo is None:
        raise ApiError(f"{name} must include a timezone.")
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def normalize_source(item: Any) -> dict[str, Any]:
    if not isinstance(item, dict) or set(item) != set(FIELDS):
        raise ApiError("Each source must use exactly the documented allowlisted fields.")
    environment = text(item["environment"], "environment", 20)
    if environment not in ENVIRONMENTS:
        raise ApiError("environment must be Development, Test, or Demo.")
    parser = text(item["parser_status"], "parser_status", 20).lower()
    if parser not in PARSER_STATES:
        raise ApiError("parser_status must be healthy, degraded, or failed.")
    expected = number(item["expected_minutes"], "expected_minutes", 1, 10_080)
    accepted = number(item["accepted_count"], "accepted_count", 0, 10_000_000)
    rejected = number(item["rejected_count"], "rejected_count", 0, 10_000_000)
    backlog = number(item["backlog_count"], "backlog_count", 0, 10_000_000)
    threshold = number(item["backlog_threshold"], "backlog_threshold", 0, 10_000_000)
    return {
        "id": ident(item["id"], "source reference"),
        "name": text(item["name"], "name", 120),
        "owner": text(item["owner"], "owner", 100),
        "environment": environment,
        "expected_minutes": expected,
        "last_seen_at": stamp(item["last_seen_at"], "last_seen_at", allow_empty=True),
        "parser_status": parser,
        "accepted_count": accepted,
        "rejected_count": rejected,
        "backlog_count": backlog,
        "backlog_threshold": threshold,
        "heartbeat_at": stamp(item["heartbeat_at"], "heartbeat_at", allow_empty=True),
        "coverage_ref": text(item["coverage_ref"], "coverage_ref", 120),
        "coverage_notes": text(item["coverage_notes"], "coverage_notes", 1_200),
    }


def parse_import(fmt: Any, content: Any) -> list[dict[str, Any]]:
    if fmt not in {"json", "csv"}:
        raise ApiError("Choose JSON or CSV format.")
    if not isinstance(content, str) or len(content.encode("utf-8")) > MAX_FILE_BYTES:
        raise ApiError("File must be UTF-8 text no larger than 512 KiB.", 413)
    try:
        if fmt == "json":
            rows = json.loads(content, object_pairs_hook=_pairs, parse_constant=_constant)
            if not isinstance(rows, list):
                raise ApiError("JSON import must be an array of source metadata objects.")
        else:
            reader = csv.DictReader(io.StringIO(content, newline=""), strict=True)
            if not reader.fieldnames or len(reader.fieldnames) != len(FIELDS) or set(reader.fieldnames) != set(FIELDS):
                raise ApiError("CSV headers must be exactly the documented source metadata fields.")
            rows = list(reader)
            if any(None in row or any(v is None for v in row.values()) for row in rows):
                raise ApiError("CSV rows have inconsistent column counts.")
    except (json.JSONDecodeError, csv.Error, RecursionError) as exc:
        raise ApiError("The file is malformed JSON or CSV.") from exc
    if not 1 <= len(rows) <= MAX_ROWS:
        raise ApiError("Import must contain between 1 and 200 source records.")
    normalized = [normalize_source(row) for row in rows]
    if len({row["id"] for row in normalized}) != len(normalized):
        raise ApiError("An import cannot contain duplicate source references.")
    return normalized


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ApiError("Duplicate JSON object keys are not accepted.")
        result[key] = value
    return result


def _constant(_: str) -> None:
    raise ApiError("Non-finite JSON numbers are not accepted.")


def assess_health(source: dict[str, Any], now: datetime | None = None) -> tuple[str, list[str], int | None]:
    """Return an explainable local state, reasons, and freshness age in minutes."""
    now = now or datetime.now(timezone.utc)
    reasons: list[str] = []
    last_seen = source["last_seen_at"]
    age: int | None = None
    stale = False
    if not last_seen:
        reasons.append("No last-seen timestamp was provided; freshness is unknown.")
    else:
        seen = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
        age = max(0, int((now - seen).total_seconds() // 60))
        allowed_age = max(source["expected_minutes"] * 2, 5)
        stale = age > allowed_age
        if stale:
            reasons.append(f"Last seen {age} minutes ago; expected interval {source['expected_minutes']} minutes, stale after {allowed_age}.")
        else:
            reasons.append(f"Freshness is within {allowed_age}-minute threshold for stated {source['expected_minutes']}-minute cadence.")
    if source["parser_status"] == "failed":
        reasons.append("Parser state is marked failed in the supplied metadata.")
    elif source["parser_status"] == "degraded":
        reasons.append("Parser state is marked degraded in the supplied metadata.")
    if source["rejected_count"] > 0:
        reasons.append(f"Supplied parser metadata reports {source['rejected_count']} rejected item(s).")
    if source["backlog_count"] > source["backlog_threshold"]:
        reasons.append(f"Backlog {source['backlog_count']} exceeds stated threshold {source['backlog_threshold']}.")
    if source["heartbeat_at"]:
        reasons.append("A heartbeat timestamp was supplied; it is not independently verified.")
    else:
        reasons.append("No heartbeat timestamp was supplied.")
    if source["parser_status"] == "failed":
        state = "failed"
    elif stale:
        state = "stale"
    elif not last_seen:
        state = "unknown"
    elif source["parser_status"] == "degraded" or source["rejected_count"] > 0 or source["backlog_count"] > source["backlog_threshold"]:
        state = "degraded"
    else:
        state = "healthy"
    return state, reasons, age


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
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY,name TEXT NOT NULL,owner TEXT NOT NULL,environment TEXT NOT NULL,
                    expected_minutes INTEGER NOT NULL,last_seen_at TEXT NOT NULL,parser_status TEXT NOT NULL,
                    accepted_count INTEGER NOT NULL,rejected_count INTEGER NOT NULL,backlog_count INTEGER NOT NULL,
                    backlog_threshold INTEGER NOT NULL,heartbeat_at TEXT NOT NULL,coverage_ref TEXT NOT NULL,
                    coverage_notes TEXT NOT NULL,updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,action TEXT NOT NULL,target_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,detail_json TEXT NOT NULL
                );
            """)

    def _audit(self, db: sqlite3.Connection, action: str, target: str, detail: dict[str, Any]) -> None:
        db.execute("INSERT INTO audit(action,target_id,created_at,detail_json) VALUES(?,?,?,?)", (action, target, utc_now(), json.dumps(detail, ensure_ascii=True, separators=(",", ":"))))

    def _insert(self, db: sqlite3.Connection, row: dict[str, Any]) -> None:
        values = [row[key] for key in FIELDS]
        db.execute("INSERT INTO sources(id,name,owner,environment,expected_minutes,last_seen_at,parser_status,accepted_count,rejected_count,backlog_count,backlog_threshold,heartbeat_at,coverage_ref,coverage_notes,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (*values, utc_now()))

    def _fixture(self) -> list[dict[str, Any]]:
        rows = json.loads((Path(__file__).resolve().parent / "samples.json").read_text(encoding="utf-8"), object_pairs_hook=_pairs)
        return [normalize_source(row) for row in rows]

    def get_state(self) -> dict[str, Any]:
        with self._connect() as db:
            rows = [dict(row) for row in db.execute("SELECT id,name,owner,environment,expected_minutes,last_seen_at,parser_status,accepted_count,rejected_count,backlog_count,backlog_threshold,heartbeat_at,coverage_ref,coverage_notes,updated_at FROM sources ORDER BY name,id LIMIT 250").fetchall()]
            for row in rows:
                row["health"], row["reasons"], row["age_minutes"] = assess_health(row)
            audit = [dict(row) for row in db.execute("SELECT id,action,target_id,created_at,detail_json FROM audit ORDER BY id DESC LIMIT 100").fetchall()]
            for row in audit:
                row["detail"] = json.loads(row.pop("detail_json"))
            return {"records": rows, "audit": audit}

    def handle_action(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action in {"load_demo", "reset_demo"}:
            if payload:
                raise ApiError("This action does not accept fields.")
            fixture = self._fixture()
            with self._connect() as db:
                if action == "load_demo":
                    if db.execute("SELECT 1 FROM sources LIMIT 1").fetchone():
                        raise ApiError("Workspace already contains sources. Choose Reset to sample to replace it.", 409)
                else:
                    db.execute("DELETE FROM sources")
                    db.execute("DELETE FROM audit")
                if action == "load_demo" and db.execute("SELECT COUNT(*) FROM audit").fetchone()[0] >= MAX_AUDIT_EVENTS:
                    raise ApiError("Local audit event limit reached; reset the demo to continue.", 413)
                for row in fixture:
                    self._insert(db, row)
                self._audit(db, "fictional_demo_loaded" if action == "load_demo" else "demo_reset", "workspace", {"count": len(fixture), "fictional": True, "previous_history_cleared": action == "reset_demo"})
            return {"message": f"Loaded {len(fixture)} fictional source-health records." if action == "load_demo" else "Local metadata and prior audit history were replaced with the fictional sample."}
        if action == "import":
            if set(payload) != {"format", "content"}:
                raise ApiError("Import requires format and content only.")
            rows = parse_import(payload["format"], payload["content"])
            try:
                with self._connect() as db:
                    count = db.execute("SELECT COUNT(*) FROM sources").fetchone()[0]
                    if count + len(rows) > MAX_WORKSPACE_RECORDS:
                        raise ApiError("Workspace is limited to 200 sources; reset the demo before adding more.", 413)
                    if db.execute("SELECT COUNT(*) FROM audit").fetchone()[0] >= MAX_AUDIT_EVENTS:
                        raise ApiError("Local audit event limit reached; reset the demo to continue.", 413)
                    for row in rows:
                        self._insert(db, row)
                    self._audit(db, "health_metadata_imported", "workspace", {"count": len(rows), "format": payload["format"]})
            except sqlite3.IntegrityError as exc:
                raise ApiError("One or more source references already exist; no rows were imported.", 409) from exc
            return {"message": f"Imported {len(rows)} fictional health metadata record(s)."}
        if action == "save_source":
            if set(payload) != set(FIELDS):
                raise ApiError("Manual source metadata contains missing or unknown fields.")
            row = normalize_source(payload)
            with self._connect() as db:
                existing = db.execute("SELECT 1 FROM sources WHERE id=?", (row["id"],)).fetchone()
                if db.execute("SELECT COUNT(*) FROM audit").fetchone()[0] >= MAX_AUDIT_EVENTS:
                    raise ApiError("Local audit event limit reached; reset the demo to continue.", 413)
                if not existing and db.execute("SELECT COUNT(*) FROM sources").fetchone()[0] >= MAX_WORKSPACE_RECORDS:
                    raise ApiError("Workspace is limited to 200 sources; reset the demo before adding more.", 413)
                if existing:
                    values = [row[key] for key in FIELDS if key != "id"]
                    db.execute("UPDATE sources SET name=?,owner=?,environment=?,expected_minutes=?,last_seen_at=?,parser_status=?,accepted_count=?,rejected_count=?,backlog_count=?,backlog_threshold=?,heartbeat_at=?,coverage_ref=?,coverage_notes=?,updated_at=? WHERE id=?", (*values, utc_now(), row["id"]))
                    event = "source_metadata_updated"
                else:
                    self._insert(db, row)
                    event = "source_metadata_added"
                self._audit(db, event, row["id"], {"health_inputs_only": True, "parser_status": row["parser_status"], "backlog": row["backlog_count"], "backlog_threshold": row["backlog_threshold"]})
            return {"message": "Local health metadata saved. No source was contacted or changed."}
        raise ApiError("Unsupported action.", 404)
