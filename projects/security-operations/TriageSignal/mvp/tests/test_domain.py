import json
import tempfile
import unittest
from pathlib import Path

from domain import ApiError, AppStore, parse_alert_import


class TriageSignalDomainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AppStore(Path(self.temp.name) / "triage.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_json_import_keeps_evidence_source_references(self):
        rows = [{"id": "a-01", "source": "Synthetic SIEM", "severity": "medium", "occurred_at": "2026-10-08T00:00:00Z", "summary": "fictional", "evidence": [{"id": "ev-1", "source": "Synthetic EDR", "observed_at": "2026-10-08T00:00:00Z", "summary": "fixture"}]}]
        self.store.handle_action("import", {"format": "json", "content": json.dumps(rows)})
        record = self.store.get_state()["records"][0]
        self.assertEqual(record["evidence"][0]["id"], "ev-1")
        self.assertEqual(record["evidence"][0]["source"], "Synthetic EDR")

    def test_csv_import_supports_pipe_delimited_evidence_references(self):
        csv = 'id,source,severity,occurred_at,summary,evidence_refs\na-02,"Synthetic SIEM",low,2026-10-08T00:00:00Z,"fictional, quoted",ev-a|ev-b\n'
        rows = parse_alert_import("csv", csv)
        self.assertEqual([e["id"] for e in rows[0]["evidence"]], ["ev-a", "ev-b"])
        self.store.handle_action("import", {"format": "csv", "content": csv})
        self.assertEqual(len(self.store.get_state()["records"]), 1)

    def test_rejects_unknown_fields_bad_severity_timezone_duplicate_json_keys_and_oversize(self):
        base = {"id": "a-1", "source": "fixture", "severity": "low", "occurred_at": "2026-10-08T00:00:00Z", "summary": "fictional"}
        with self.assertRaises(ApiError): parse_alert_import("json", json.dumps([{**base, "unexpected": "x"}]))
        with self.assertRaises(ApiError): parse_alert_import("json", json.dumps([{**base, "severity": "extreme"}]))
        with self.assertRaises(ApiError): parse_alert_import("json", json.dumps([{**base, "occurred_at": "2026-10-08T00:00:00"}]))
        with self.assertRaises(ApiError): parse_alert_import("json", '[{"id":"x","id":"y"}]')
        with self.assertRaises(ApiError): parse_alert_import("csv", "x" * (512 * 1024 + 1))

    def test_status_note_and_audit_persist_across_reopen(self):
        self.store.handle_action("load_demo", {})
        self.store.handle_action("save_alert", {"id": "alert-demo-1042", "status": "reviewed", "analyst_note": "Reviewed against evidence-demo-01; <script> remains plain text.", "citations": ["evidence-demo-01"]})
        reopened = AppStore(self.store.path)
        state = reopened.get_state()
        row = next(x for x in state["records"] if x["id"] == "alert-demo-1042")
        self.assertEqual(row["status"], "reviewed")
        self.assertIn("<script>", row["analyst_note"])
        self.assertEqual(row["citations"], ["evidence-demo-01"])
        event = next(x for x in state["audit"] if x["action"] == "alert_review_updated")
        self.assertEqual(event["detail"]["to"], "reviewed")
        self.assertEqual(event["detail"]["citations"], ["evidence-demo-01"])

    def test_sql_injection_like_summary_is_data_and_duplicate_import_is_atomic(self):
        summary = 'synthetic "; DROP TABLE alerts;-- <img src=x onerror=alert(1)>'
        row = {"id": "a-safe", "source": "fixture", "severity": "low", "occurred_at": "2026-10-08T00:00:00Z", "summary": summary}
        self.store.handle_action("import", {"format": "json", "content": json.dumps([row])})
        saved = self.store.get_state()["records"][0]["summary"]
        self.assertEqual(saved, summary)
        with self.assertRaises(ApiError): self.store.handle_action("import", {"format": "json", "content": json.dumps([row])})
        self.assertEqual(len(self.store.get_state()["records"]), 1)

    def test_completed_review_requires_a_real_source_or_evidence_citation(self):
        self.store.handle_action("load_demo", {})
        payload = {"id": "alert-demo-1042", "status": "reviewed", "analyst_note": "Fictional analyst review."}
        with self.assertRaises(ApiError): self.store.handle_action("save_alert", {**payload, "citations": []})
        with self.assertRaises(ApiError): self.store.handle_action("save_alert", {**payload, "citations": ["evidence-from-another-alert"]})
        self.store.handle_action("save_alert", {**payload, "citations": ["alert:alert-demo-1042"]})
        record = next(row for row in self.store.get_state()["records"] if row["id"] == "alert-demo-1042")
        self.assertEqual(record["citations"], ["alert:alert-demo-1042"])

    def test_reset_replaces_notes_and_history_with_fictional_new_status_rows(self):
        self.store.handle_action("load_demo", {})
        self.store.handle_action("save_alert", {"id": "alert-demo-1042", "status": "in_review", "analyst_note": "fictional note", "citations": []})
        self.store.handle_action("reset_demo", {})
        state = self.store.get_state()
        self.assertTrue(all(row["status"] == "new" and row["analyst_note"] == "" for row in state["records"]))
        self.assertEqual([row["action"] for row in state["audit"]], ["demo_reset"])
        with self.assertRaises(ApiError): self.store.handle_action("save_alert", {"id": "alert-demo-1042", "status": "invalid", "analyst_note": "x" * 4001})


    def test_total_workspace_record_cap_applies_across_import_batches(self):
        rows = [{"id": f"cap-{i}", "source": "Synthetic source", "severity": "low", "occurred_at": "2026-10-08T00:00:00Z", "summary": "fictional"} for i in range(200)]
        self.store.handle_action("import", {"format": "json", "content": json.dumps(rows)})
        extra = {"id": "cap-extra", "source": "Synthetic source", "severity": "low", "occurred_at": "2026-10-08T00:00:00Z", "summary": "fictional"}
        with self.assertRaises(ApiError): self.store.handle_action("import", {"format": "json", "content": json.dumps([extra])})
        self.assertEqual(len(self.store.get_state()["records"]), 200)

if __name__ == "__main__":
    unittest.main()
