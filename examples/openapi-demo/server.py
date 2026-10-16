#!/usr/bin/env python3
"""
Veriflow OpenAPI Contract Verification Demo Server.

A deterministic, lightweight local HTTP server built on Python standard library.
Supports clean execution against openapi.json/openapi.yaml contracts and targeted
fault injection modes to demonstrate reliable detection of contract violations:
  - missing_field: GET /api/items omits the required 'price' field
  - wrong_status: GET /api/health returns HTTP 500 instead of documented 200
  - wrong_content_type: GET /api/health returns text/plain instead of application/json
  - invalid_type: GET /api/profile returns string for 'active' instead of boolean
  - request_validation: POST /api/items returns 500 on invalid input instead of 400
"""

from __future__ import annotations

from http.server import HTTPServer
import json
from pathlib import Path
import sys
import threading
from typing import Any, Dict, Optional
from urllib.parse import urlparse

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from skills.veriflow.demo_app.server import DemoAppHandler, DemoServer


class OpenApiDemoHandler(DemoAppHandler):
    """HTTP handler with targeted contract fault injection modes for OpenAPI verification."""

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        fault = self.server_config.get("fault", "")

        # Fault Mode: missing_field on /api/items
        if fault in ("missing_field", "fault_missing_field") and path == "/api/items":
            # Omits required 'price' property from Item schema
            broken_items = [
                {"id": 1, "name": "Standard Widget", "category": "Tools"},
                {"id": 2, "name": "Deluxe Gadget", "category": "Electronics"},
            ]
            self._send_json(200, broken_items)
            return

        # Fault Mode: wrong_status on /api/health
        if fault in ("wrong_status", "fault_wrong_status") and path == "/api/health":
            # Returns undocumented 500 status code
            self._send_json(500, {
                "error": "Unexpected server failure",
                "code": "INTERNAL_SERVER_ERROR",
            })
            return

        # Fault Mode: wrong_content_type on /api/health
        if fault in ("wrong_content_type", "fault_wrong_content_type") and path == "/api/health":
            # Returns text/plain instead of application/json
            body = b"OK - Healthy Service"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # Fault Mode: invalid_type on /api/profile
        if fault in ("invalid_type", "fault_invalid_type") and path == "/api/profile":
            auth = self._get_auth_user()
            username, role = auth or ("alice", "user")
            # Returns string "yes" for boolean property 'active'
            self._send_json(200, {
                "username": username,
                "role": role,
                "email": f"{username}@example.local",
                "active": "yes",  # Contract violation: expected boolean
            })
            return

        # Default clean implementation
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        fault = self.server_config.get("fault", "")

        # Fault Mode: request_validation on POST /api/items
        if fault in ("request_validation", "fault_request_validation") and path == "/api/items":
            body = self._parse_body()
            name = str(body.get("name", "")).strip()
            # If invalid, crash with 500 instead of returning documented 400 ErrorResponse
            if not name or "price" not in body:
                self._send_json(500, {
                    "error": "Unhandled NullReferenceException: price is null",
                    "code": "SERVER_CRASH",
                })
                return

        super().do_POST()


class OpenApiDemoServer:
    """Manager for the OpenAPI verification demo HTTP fixture."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0, fault: str = ""):
        self.host = host
        self.port = port
        self.fault = fault
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> str:
        self._server = HTTPServer((self.host, self.port), OpenApiDemoHandler)
        self._server.server_config = {"fault": self.fault}
        self.port = self._server.server_address[1]

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.get_url()

    def get_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            self._thread = None


if __name__ == "__main__":
    port = 8080
    fault = ""
    if len(sys.argv) > 1 and sys.argv[1].startswith("--fault="):
        fault = sys.argv[1].split("=", 1)[1]
    elif len(sys.argv) > 2 and sys.argv[1] == "--fault":
        fault = sys.argv[2]

    server = OpenApiDemoServer(port=port, fault=fault)
    url = server.start()
    print(f"Veriflow OpenAPI Demo Server running at: {url} (fault: '{fault or 'none'}')")
    print("Press Ctrl+C to stop.")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
