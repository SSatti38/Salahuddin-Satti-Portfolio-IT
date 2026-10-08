import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from domain import ApiError, AppStore, assess_health, parse_import


def source(source_id="source-demo-1"):
    return {"id": source_id, "name": "Fictional source", "owner": "Demo owner", "environment": "Demo", "expected_minutes": 15, "last_seen_at": "2026-10-08T00:00:00Z", "parser_status": "healthy", "accepted_count": 100, "rejected_count": 0, "backlog_count": 2, "backlog_threshold": 20, "heartbeat_at": "2026-10-08T00:00:00Z", "coverage_ref": "VIS-DEMO-01", "coverage_notes": "Fictional mapping evidence only."}


class LogPulseDomainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AppStore(Path(self.temp.name) / "logpulse.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_json_csv_import_and_strict_input_limits(self):
        row = source()
        self.assertEqual(parse_import("json", json.dumps([row]))[0]["id"], "source-demo-1")
        csv_row = {key: str(value) for key, value in row.items()}
        header = ",".join(row.keys())
        line = ",".join('"' + csv_row[key].replace('"', '""') + '"' for key in row)
        self.assertEqual(parse_import("csv", header + "\n" + line + "\n")[0]["id"], "source-demo-1")
        with self.assertRaises(ApiError): parse_import("json", json.dumps([{**row, "unexpected": 1}]))
        with self.assertRaises(ApiError): parse_import("json", json.dumps([{**row, "expected_minutes": 0}]))
        with self.assertRaises(ApiError): parse_import("json", "x" * (512 * 1024 + 1))
        with self.assertRaises(ApiError): parse_import("json", json.dumps([source(str(i)) for i in range(201)]))

    def test_health_thresholds_are_explainable(self):
        now = datetime(2026, 10, 8, 1, 0, tzinfo=timezone.utc)
        recent = {**source(), "last_seen_at": "2026-10-08T00:50:00Z", "heartbeat_at": "2026-10-08T00:51:00Z"}
        self.assertEqual(assess_health(recent, now)[0], "healthy")
        stale = {**recent, "last_seen_at": "2026-10-08T00:00:00Z"}
        self.assertEqual(assess_health(stale, now)[0], "stale")
        degraded = {**recent, "parser_status": "degraded", "rejected_count": 2, "backlog_count": 21}
        state, reasons, _ = assess_health(degraded, now)
        self.assertEqual(state, "degraded")
        self.assertTrue(any("threshold 20" in reason for reason in reasons))
        failed = {**recent, "parser_status": "failed"}
        self.assertEqual(assess_health(failed, now)[0], "failed")

    def test_manual_update_and_audit_are_local_and_persistent(self):
        self.store.handle_action("save_source", source())
        updated = {**source(), "parser_status": "degraded", "rejected_count": 3}
        self.store.handle_action("save_source", updated)
        reopened = AppStore(self.store.path)
        state = reopened.get_state()
        self.assertEqual(state["records"][0]["parser_status"], "degraded")
        self.assertEqual([a["action"] for a in state["audit"]], ["source_metadata_updated", "source_metadata_added"])

    def test_sql_injection_like_text_is_literal_and_bad_value_rejected(self):
        row = {**source(), "coverage_notes": "x'); DROP TABLE sources;-- <script>alert(1)</script>"}
        self.store.handle_action("import", {"format": "json", "content": json.dumps([row])})
        self.assertEqual(self.store.get_state()["records"][0]["coverage_notes"], row["coverage_notes"])
        with self.assertRaises(ApiError): self.store.handle_action("save_source", {**source(), "backlog_count": "1 OR 1=1"})
        self.assertEqual(len(self.store.get_state()["records"]), 1)

    def test_reset_demo_replaces_local_metadata_and_audit(self):
        self.store.handle_action("load_demo", {})
        self.store.handle_action("save_source", {**source("manual-1"), "name": "Temporary fictional source"})
        self.store.handle_action("reset_demo", {})
        state = self.store.get_state()
        self.assertEqual({r["id"] for r in state["records"]}, {"source-demo-edge", "source-demo-cloud", "source-demo-app"})
        self.assertEqual([event["action"] for event in state["audit"]], ["demo_reset"])


    def test_total_workspace_source_cap_applies_across_import_batches(self):
        rows = [source(f"cap-{i}") for i in range(200)]
        self.store.handle_action("import", {"format": "json", "content": json.dumps(rows)})
        with self.assertRaises(ApiError): self.store.handle_action("import", {"format": "json", "content": json.dumps([source("cap-extra")])})
        self.assertEqual(len(self.store.get_state()["records"]), 200)

if __name__ == "__main__":
    unittest.main()
