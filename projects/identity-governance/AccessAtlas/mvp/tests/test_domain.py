import csv
import io
import json
import tempfile
import unittest
from pathlib import Path

from domain import ApiError, AppStore, parse_import


def identity(identity_id="id-demo-1"):
    return {"id": identity_id, "display_name": "Fictional Person", "account_state": "active", "last_sign_in": "2026-10-07T00:00:00Z", "entitlement": "Demo-Reader", "source": "Synthetic directory", "snapshot_at": "2026-10-08T00:00:00Z", "evidence": "Fictional snapshot evidence."}


class AccessAtlasDomainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = AppStore(Path(self.temp.name) / "atlas.sqlite3")

    def tearDown(self):
        self.temp.cleanup()

    def test_json_and_csv_snapshot_import(self):
        row = identity()
        self.store.handle_action("import", {"format": "json", "content": json.dumps([row])})
        self.assertEqual(self.store.get_state()["records"][0]["source"], "Synthetic directory")
        fields = ["id", "display_name", "account_state", "last_sign_in", "entitlement", "source", "snapshot_at", "evidence"]
        buffer = io.StringIO(); writer = csv.DictWriter(buffer, fieldnames=fields); writer.writeheader(); writer.writerow(identity("id-demo-2"))
        parsed = parse_import("csv", buffer.getvalue())
        self.assertEqual(parsed[0]["id"], "id-demo-2")

    def test_rejects_invalid_state_unknown_field_and_file_or_row_caps(self):
        row = identity()
        with self.assertRaises(ApiError): parse_import("json", json.dumps([{**row, "account_state": "compromised"}]))
        with self.assertRaises(ApiError): parse_import("json", json.dumps([{**row, "tenant_id": "other"}]))
        with self.assertRaises(ApiError): parse_import("json", "x" * (512 * 1024 + 1))
        with self.assertRaises(ApiError): parse_import("json", json.dumps([identity(str(i)) for i in range(201)]))

    def test_human_decision_creates_separate_history_and_audit(self):
        self.store.handle_action("import", {"format": "json", "content": json.dumps([identity()])})
        decision = {"id": "id-demo-1", "outcome": "follow_up", "reviewer": "Reviewer A", "rationale": "Fictional rationale based on source snapshot evidence."}
        self.store.handle_action("review", decision)
        self.store.handle_action("review", {**decision, "outcome": "retain", "rationale": "Second human decision supersedes the first in sequence."})
        state = self.store.get_state()
        row = state["records"][0]
        self.assertEqual(row["latest_outcome"], "retain")
        self.assertEqual(len(row["decisions"]), 2)
        self.assertEqual(row["decisions"][1]["rationale"], decision["rationale"])
        audit = next(event for event in state["audit"] if event["action"] == "review_decision_recorded")
        self.assertIn("decision_id", audit["detail"])

    def test_sql_injection_like_text_is_literal_and_persistence_works(self):
        payload = identity("identity-1"); payload["display_name"] = "x' OR 1=1; DROP TABLE identities;-- <script>alert(1)</script>"
        self.store.handle_action("import", {"format": "json", "content": json.dumps([payload])})
        reopened = AppStore(self.store.path)
        self.assertEqual(reopened.get_state()["records"][0]["display_name"], payload["display_name"])
        self.assertEqual(len(reopened.get_state()["records"]), 1)

    def test_invalid_decision_does_not_modify_data_and_reset_clears_history(self):
        self.store.handle_action("load_demo", {})
        with self.assertRaises(ApiError): self.store.handle_action("review", {"id": "identity-demo-017", "outcome": "disable", "reviewer": "R", "rationale": "x"})
        self.store.handle_action("review", {"id": "identity-demo-017", "outcome": "retain", "reviewer": "R", "rationale": "Fictional review."})
        self.store.handle_action("reset_demo", {})
        state = self.store.get_state()
        self.assertTrue(all(not row["decisions"] and row["latest_outcome"] is None for row in state["records"]))
        self.assertEqual([event["action"] for event in state["audit"]], ["demo_reset"])


    def test_total_workspace_identity_cap_applies_across_import_batches(self):
        rows = [identity(f"cap-{i}") for i in range(200)]
        self.store.handle_action("import", {"format": "json", "content": json.dumps(rows)})
        with self.assertRaises(ApiError): self.store.handle_action("import", {"format": "json", "content": json.dumps([identity("cap-extra")])})
        self.assertEqual(len(self.store.get_state()["records"]), 200)

if __name__ == "__main__":
    unittest.main()
