#!/usr/bin/env python3
"""Tiny loopback-only HTTP shell for a local, single-user synthetic-data MVP."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from domain import AppStore, ApiError

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / ".local-ui"
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "workspace.sqlite3"
MAX_REQUEST_BYTES = 1_100_000


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ValueError("Non-finite JSON numbers are not accepted")


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class AppHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Local-MVP"
    sys_version = ""

    def version_string(self) -> str:
        return self.server_version

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, fmt: str, *args: Any) -> None:
        # Do not log request bodies, imported content, notes, or query strings.
        print(f"[local-mvp] {self.client_address[0]} {self.command} {self.path.split('?')[0]} - {fmt % args}")

    @property
    def store(self) -> AppStore:
        return self.server.store  # type: ignore[attr-defined]

    @property
    def csrf_token(self) -> str:
        return self.server.csrf_token  # type: ignore[attr-defined]

    @property
    def expected_host(self) -> str:
        return self.server.expected_host  # type: ignore[attr-defined]

    def _headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        self.send_header("X-DNS-Prefetch-Control", "off")

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self._headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        self.wfile.write(body)

    def _json(self, status: int, value: Any) -> None:
        body = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8")

    def _host_ok(self) -> bool:
        hosts = self.headers.get_all("Host", [])
        return len(hosts) == 1 and hosts[0].strip().lower() == self.expected_host.lower()

    def _fail(self, status: int, message: str) -> None:
        self._json(status, {"ok": False, "error": message})

    def do_GET(self) -> None:
        if not self._host_ok():
            self._fail(400, "This local app accepts only its configured loopback host.")
            return
        if self.path == "/":
            self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/app.css":
            self._send(200, (STATIC / "app.css").read_bytes(), "text/css; charset=utf-8")
        elif self.path == "/app.js":
            self._send(200, (STATIC / "app.js").read_bytes(), "text/javascript; charset=utf-8")
        elif self.path == "/api/state":
            state = self.store.get_state()
            state["csrf_token"] = self.csrf_token
            self._json(200, {"ok": True, "state": state})
        else:
            self._fail(404, "Not found.")

    def do_POST(self) -> None:
        if not self._host_ok():
            self._fail(400, "This local app accepts only its configured loopback host.")
            return
        origins = self.headers.get_all("Origin", [])
        if len(origins) != 1 or origins[0] != f"http://{self.expected_host}":
            self._fail(403, "A same-origin request is required.")
            return
        if self.headers.get("Sec-Fetch-Site", "") != "same-origin":
            self._fail(403, "A same-origin browser request is required.")
            return
        tokens = self.headers.get_all("X-Local-Token", [])
        if len(tokens) != 1 or not secrets.compare_digest(tokens[0], self.csrf_token):
            self._fail(403, "The local request token is missing or invalid. Reload the app and try again.")
            return
        if self.path != "/api/action":
            self._fail(404, "Not found.")
            return
        content_types = self.headers.get_all("Content-Type", [])
        if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != "application/json":
            self._fail(415, "Send a JSON request.")
            return
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isdigit():
            self._fail(411, "A single valid Content-Length is required.")
            return
        size = int(lengths[0])
        if size < 2 or size > MAX_REQUEST_BYTES:
            self._fail(413, "Request exceeds the local size limit.")
            return
        try:
            raw = self.rfile.read(size)
            if len(raw) != size:
                raise ValueError("Incomplete request body")
            request = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_object_no_duplicates, parse_constant=_reject_constant)
            if not isinstance(request, dict) or set(request) != {"action", "payload"}:
                raise ValueError("Request must contain only action and payload")
            if not isinstance(request["action"], str) or len(request["action"]) > 48 or not isinstance(request["payload"], dict):
                raise ValueError("Invalid action or payload")
            result = self.store.handle_action(request["action"], request["payload"])
            state = self.store.get_state()
            state["csrf_token"] = self.csrf_token
            self._json(200, {"ok": True, "result": result, "state": state})
        except ApiError as exc:
            self._fail(exc.status, str(exc))
        except (UnicodeError, json.JSONDecodeError, ValueError, RecursionError):
            self._fail(400, "The request is malformed or contains invalid input.")
        except sqlite3.Error:
            self._fail(500, "Local storage could not complete the request.")
        except Exception:
            self._fail(500, "The local app encountered an unexpected error.")


def serve(host: str = "127.0.0.1", port: int = 8761) -> None:
    if host != "127.0.0.1":
        raise SystemExit("For safety, this MVP can bind only to 127.0.0.1.")
    if not 1024 <= port <= 65535:
        raise SystemExit("Choose a local port between 1024 and 65535.")
    DATA_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        os.chmod(DATA_DIR, 0o700)
    except OSError:
        pass
    store = AppStore(DB_PATH)
    token = secrets.token_urlsafe(32)
    server = LocalServer((host, port), AppHandler)
    server.store = store  # type: ignore[attr-defined]
    server.csrf_token = token  # type: ignore[attr-defined]
    server.expected_host = f"127.0.0.1:{server.server_address[1]}"  # type: ignore[attr-defined]
    try:
        os.chmod(DB_PATH, 0o600)
    except OSError:
        pass
    print(f"Local-only app listening at http://{server.expected_host}/")
    print("Synthetic data only. No authentication, tenant isolation, encryption-at-rest, integrations, or external network access.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping local app.")
    finally:
        server.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run this single-user MVP on loopback only.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8761)
    args = parser.parse_args()
    serve(args.host, args.port)
