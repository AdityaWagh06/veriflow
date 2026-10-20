#!/usr/bin/env python3
"""
Deterministic local fixture for Veriflow's live security checks.

Serves the same small application in two modes on an ephemeral loopback port:

- ``secure`` (default): sends security headers, flags its session cookie,
  encodes reflected input, refuses anonymous access to the protected path,
  scopes record lookups to the authenticated owner, returns a generic error
  body, rejects external redirect destinations, and requires a CSRF token.
- ``insecure``: each of those behaviours is individually broken, selected by
  name, so a test can prove a specific check fails for the expected reason.

Everything here is synthetic: the two accounts are fictional and the tokens are
fixed literals that exist only to exercise an authorization branch. The server
binds to 127.0.0.1 only and holds all state in memory.

The credential-shaped literals in this file are fixture data, not secrets. They
carry the inline marker Veriflow's static scanner honours so a scan of this
repository reports them as suppressed rather than as findings.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from html import escape
from typing import Any, Dict, Optional, Set
from urllib.parse import parse_qs, urlparse

#: Fault names the insecure mode understands. Each one breaks exactly one check.
FAULT_MODES: Set[str] = {
    "missing_headers",
    "insecure_cookie",
    "reflected_xss",
    "open_protected_route",
    "cross_user_leak",
    "stack_trace_leak",
    "secret_in_response",
    "open_redirect",
    "missing_csrf",
}

#: Two fictional accounts. The tokens are fixture literals, never real credentials.
SYNTHETIC_USERS: Dict[str, Dict[str, Any]] = {
    "vf-token-user-a": {"user_id": "user-a", "display": "Ada Fixture"},  # veriflow: allow-security
    "vf-token-user-b": {"user_id": "user-b", "display": "Bo Fixture"},  # veriflow: allow-security
}

#: Records owned by each synthetic account.
SYNTHETIC_RECORDS: Dict[str, Dict[str, Any]] = {
    "user-a": {"record_id": "rec-a", "owner": "user-a", "note": "Ada's private note"},
    "user-b": {"record_id": "rec-b", "owner": "user-b", "note": "Bo's private note"},
}

#: Issued to the login response in secure mode; a fixture value, not a secret.
SESSION_COOKIE_VALUE = "vf-session-fixture"  # veriflow: allow-security

#: Accepted CSRF token in secure mode; a fixture value, not a secret.
CSRF_TOKEN = "vf-csrf-fixture"  # veriflow: allow-security


class SecurityFixtureHandler(BaseHTTPRequestHandler):
    """Request handler whose behaviour is driven by the server's fault set."""

    protocol_version = "HTTP/1.1"

    # -- helpers ---------------------------------------------------------- #

    @property
    def faults(self) -> Set[str]:
        return getattr(self.server, "faults", set())

    def log_message(self, fmt: str, *args: Any) -> None:
        """Silence per-request logging so test output stays readable."""
        return

    def _security_headers(self) -> Dict[str, str]:
        """Return the browser-protection headers, unless that fault is active."""
        if "missing_headers" in self.faults:
            return {}
        return {
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
        }

    def _send(
        self,
        status: int,
        body: str,
        content_type: str = "application/json",
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        for key, value in self._security_headers().items():
            self.send_header(key, value)
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(payload)

    def _json(self, status: int, payload: Dict[str, Any], **kwargs: Any) -> None:
        self._send(status, json.dumps(payload), "application/json", **kwargs)

    def _bearer_token(self) -> Optional[str]:
        header = self.headers.get("Authorization", "")
        if header.lower().startswith("bearer "):
            return header[7:].strip()
        return None

    def _read_body(self) -> bytes:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            return b""
        return self.rfile.read(length) if length > 0 else b""

    # -- routes ----------------------------------------------------------- #

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/":
            if "secret_in_response" in self.faults:
                # A key that was only ever meant for server use, embedded in the page.
                body = (
                    '{"app":"veriflow-security-fixture",'
                    '"stripe_api_key":"zQ8mLvRxTn2wKp9sYd4hGj7bFe3uCi6a"}'  # veriflow: allow-security
                )
            else:
                body = '{"app":"veriflow-security-fixture","status":"ok"}'
            self._json(200, json.loads(body))
            return

        if path == "/health":
            self._json(200, {"status": "healthy"})
            return

        if path == "/echo":
            value = (query.get("q") or [""])[0]
            if "reflected_xss" in self.faults:
                # Interpolates the raw value straight into markup.
                html = f"<html><body><p>You searched for: {value}</p></body></html>"
            else:
                html = f"<html><body><p>You searched for: {escape(value)}</p></body></html>"
            self._send(200, html, "text/html; charset=utf-8")
            return

        if path == "/account":
            if "open_protected_route" in self.faults:
                self._json(200, {"account": "exposed-without-credentials"})
                return
            token = self._bearer_token()
            if token not in SYNTHETIC_USERS:
                self._json(401, {"error": "authentication required"})
                return
            self._json(200, {"account": SYNTHETIC_USERS[token]["display"]})
            return

        if path.startswith("/records/"):
            record_id = path.rsplit("/", 1)[-1]
            record = next(
                (r for r in SYNTHETIC_RECORDS.values() if r["record_id"] == record_id),
                None,
            )
            if record is None:
                self._json(404, {"error": "not found"})
                return

            token = self._bearer_token()
            if token not in SYNTHETIC_USERS:
                self._json(401, {"error": "authentication required"})
                return

            if "cross_user_leak" in self.faults:
                # Authenticates the caller, then never checks ownership.
                self._json(200, record)
                return

            caller = SYNTHETIC_USERS[token]["user_id"]
            if record["owner"] != caller:
                self._json(404, {"error": "not found"})
                return
            self._json(200, record)
            return

        if path == "/boom":
            if "stack_trace_leak" in self.faults:
                trace = (
                    "Traceback (most recent call last):\n"
                    '  File "/srv/app/handlers.py", line 42, in handle\n'
                    "    raise RuntimeError(connection_string)\n"
                    "RuntimeError: postgresql://admin:Qx7LbN4tKp8s@db.internal:5432/app\n"  # veriflow: allow-security
                )
                self._send(500, trace, "text/plain; charset=utf-8")
                return
            self._json(500, {"error": "internal error", "correlation_id": "vf-0001"})
            return

        if path == "/go":
            destination = (query.get("next") or [""])[0]
            if "open_redirect" in self.faults:
                self.send_response(302)
                self.send_header("Location", destination or "/")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if destination.startswith("/") and not destination.startswith("//"):
                self.send_response(302)
                self.send_header("Location", destination)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            self._json(400, {"error": "redirect destination must be a relative path"})
            return

        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        path = parsed.path
        self._read_body()

        if path == "/login":
            if "insecure_cookie" in self.faults:
                cookie = f"session={SESSION_COOKIE_VALUE}; Path=/"
            else:
                cookie = f"session={SESSION_COOKIE_VALUE}; Path=/; HttpOnly; SameSite=Lax"
            self._json(200, {"status": "authenticated"}, extra_headers={"Set-Cookie": cookie})
            return

        if path == "/profile/update":
            if "missing_csrf" in self.faults:
                self._json(200, {"status": "updated"})
                return
            supplied = self.headers.get("X-CSRF-Token", "")
            if supplied != CSRF_TOKEN:
                self._json(403, {"error": "missing or invalid CSRF token"})
                return
            self._json(200, {"status": "updated"})
            return

        self._json(404, {"error": "not found"})


class SecurityFixtureServer:
    """Context manager that runs the fixture on an ephemeral loopback port.

    Args:
        faults: Fault names to activate. An empty set serves the secure variant.

    Raises:
        ValueError: when a fault name is not recognised, so a typo in a test
            cannot silently produce a passing (secure) server.
    """

    def __init__(self, faults: Optional[Set[str]] = None) -> None:
        requested = set(faults or set())
        unknown = sorted(requested - FAULT_MODES)
        if unknown:
            raise ValueError(
                f"Unknown fault mode(s): {', '.join(unknown)}. Available: {', '.join(sorted(FAULT_MODES))}"
            )
        self.faults = requested
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self.port: int = 0

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> "SecurityFixtureServer":
        # Port 0 lets the OS choose a free port, so parallel runs cannot collide.
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), SecurityFixtureHandler)
        self._server.faults = self.faults  # type: ignore[attr-defined]
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self) -> "SecurityFixtureServer":
        return self.start()

    def __exit__(self, *exc_info: Any) -> None:
        self.stop()


def main() -> int:
    """Run the fixture in the foreground for manual inspection."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the Veriflow local security fixture on 127.0.0.1."
    )
    parser.add_argument(
        "--fault",
        action="append",
        dest="faults",
        default=[],
        help=f"Activate a fault (repeatable). Available: {', '.join(sorted(FAULT_MODES))}",
    )
    args = parser.parse_args()

    try:
        server = SecurityFixtureServer(set(args.faults)).start()
    except ValueError as exc:
        print(f"Error: {exc}")
        return 2

    mode = ", ".join(sorted(server.faults)) if server.faults else "secure (no faults)"
    print(f"Veriflow security fixture listening on {server.base_url}  [mode: {mode}]")
    print("Press Ctrl+C to stop.")
    try:
        while True:
            threading.Event().wait(1.0)
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
