import http.client
import json
import os
import stat
import tempfile
import threading
import unittest
from pathlib import Path

from core import AppHandler, LocalServer, MAX_REQUEST_BYTES
from domain import AppStore


class LocalHttpSecurityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store = AppStore(Path(cls.temp.name) / "http.sqlite3")
        cls.token = "test-token-not-a-secret"
        cls.server = LocalServer(("127.0.0.1", 0), AppHandler)
        cls.server.store = cls.store
        cls.server.csrf_token = cls.token
        cls.server.expected_host = f"127.0.0.1:{cls.server.server_address[1]}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.temp.cleanup()

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        data = response.read()
        result = response.status, dict(response.getheaders()), data
        conn.close()
        return result

    def base_headers(self):
        return {"Origin": f"http://127.0.0.1:{self.port}", "Sec-Fetch-Site": "same-origin", "X-Local-Token": self.token, "Content-Type": "application/json"}

    def test_static_response_has_strict_security_headers_and_no_external_scripts(self):
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        lower = {key.lower(): value for key, value in headers.items()}
        self.assertIn("default-src 'self'", lower["content-security-policy"])
        self.assertEqual(lower["x-frame-options"], "DENY")
        self.assertEqual(lower["x-content-type-options"], "nosniff")
        self.assertNotIn(b"https://", body)
        self.assertNotIn(b"style=", body)
        js_status, _, js_body = self.request("GET", "/app.js")
        self.assertEqual(js_status, 200)
        self.assertNotIn(b"innerHTML", js_body)
        self.assertNotIn(b"https://", js_body)

    def test_workspace_folder_and_database_permissions_are_restricted_on_posix(self):
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(self.store.path.parent.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(self.store.path.stat().st_mode), 0o600)

    def test_valid_local_token_origin_and_fetch_metadata_allow_action(self):
        payload = json.dumps({"action": "load_demo", "payload": {}})
        status, _, body = self.request("POST", "/api/action", payload, self.base_headers())
        self.assertEqual(status, 200, body)
        self.assertTrue(json.loads(body)["ok"])

    def test_cross_origin_and_wrong_token_are_rejected(self):
        payload = json.dumps({"action": "load_demo", "payload": {}})
        headers = self.base_headers(); headers["Origin"] = "https://attacker.example"
        self.assertEqual(self.request("POST", "/api/action", payload, headers)[0], 403)
        headers = self.base_headers(); headers["X-Local-Token"] = "wrong"
        self.assertEqual(self.request("POST", "/api/action", payload, headers)[0], 403)

    def test_unexpected_host_and_unmapped_file_path_are_rejected(self):
        headers = {"Host": "attacker.example"}
        self.assertEqual(self.request("GET", "/", headers=headers)[0], 400)
        self.assertEqual(self.request("GET", "/static/../../domain.py")[0], 404)

    def test_declared_oversize_body_is_rejected_before_read(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        conn.putrequest("POST", "/api/action")
        for key, value in self.base_headers().items():
            conn.putheader(key, value)
        conn.putheader("Content-Length", str(MAX_REQUEST_BYTES + 1))
        conn.endheaders()
        response = conn.getresponse()
        self.assertEqual(response.status, 413)
        response.read(); conn.close()


if __name__ == "__main__":
    unittest.main()
