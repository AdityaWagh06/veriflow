#!/usr/bin/env python3
"""
Veriflow Deterministic Local Demo Web & API Application.

A lightweight, zero-dependency HTTP server built with Python's standard library.
Provides realistic web pages, RESTful API endpoints, form handling, session cookies,
route guards, and controlled fault injection modes for browser and API automation testing.
"""

from __future__ import annotations

from http import cookies
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import threading
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse


class DemoAppHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Veriflow demo web and API application."""

    @property
    def server_config(self) -> Dict[str, Any]:
        return getattr(self.server, "server_config", {})

    @property
    def items_db(self) -> Dict[int, Dict[str, Any]]:
        if not hasattr(self.server, "items_db"):
            self.server.items_db = {
                1: {"id": 1, "name": "Standard Widget", "price": 19.99, "category": "Tools"},
                2: {"id": 2, "name": "Deluxe Gadget", "price": 49.99, "category": "Electronics"},
            }
        return self.server.items_db

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard HTTP server logging to keep test output clean."""
        pass

    def _get_cookie(self, name: str) -> Optional[str]:
        cookie_header = self.headers.get("Cookie")
        if not cookie_header:
            return None
        c = cookies.SimpleCookie()
        try:
            c.load(cookie_header)
            if name in c:
                return c[name].value
        except Exception:
            return None
        return None

    def _get_auth_user(self) -> Optional[Tuple[str, str]]:
        """Extract authenticated user and role from Bearer token or session cookie.

        Returns (username, role) or None.
        """
        # 1. Check Authorization header
        auth_header = self.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            if token == "token_admin":
                return ("admin", "admin")
            elif token == "token_user":
                return ("alice", "user")
            elif token.startswith("user_"):
                return (token[5:], "user")

        # 2. Check Session Cookie
        cookie_user = self._get_cookie("vf_session")
        if cookie_user:
            role = "admin" if cookie_user == "admin" else "user"
            return (cookie_user, role)

        return None

    def _parse_body(self) -> Dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length).decode("utf-8")
        content_type = self.headers.get("Content-Type", "")

        if "application/json" in content_type:
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"_raw": raw, "_invalid_json": True}

        # URL-encoded form data fallback
        parsed = parse_qs(raw)
        return {k: v[0] for k, v in parsed.items()}

    def _send_html(self, status: int, html: str, extra_headers: Optional[list] = None) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for k, v in extra_headers:
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, status: int, data: Any, extra_headers: Optional[list] = None) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        if extra_headers:
            for k, v in extra_headers:
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        fault = query.get("fault", [self.server_config.get("fault", "")])[0]

        # Common HTML layout wrapper
        def layout(title: str, content: str, has_js_error: bool = False) -> str:
            js_error_tag = '<script>console.error("Deliberate client error in page"); throw new Error("Simulated JS error");</script>' if has_js_error else ""
            session_user = self._get_cookie("vf_session")
            auth_link = (
                f'<span id="user-greeting">Hello, <b>{session_user}</b></span> | <a id="logout-btn" href="/logout">Logout</a>'
                if session_user
                else '<a id="nav-login" href="/login">Login</a> | <a id="nav-register" href="/register">Register</a>'
            )
            return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{title} — Veriflow Demo</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; margin: 0; padding: 0; background: #f8fafc; color: #1e293b; }}
    header {{ background: #0f172a; color: white; padding: 1rem 2rem; display: flex; justify-content: space-between; align-items: center; }}
    header a {{ color: #38bdf8; text-decoration: none; margin-left: 1rem; }}
    nav {{ display: flex; gap: 1rem; align-items: center; }}
    main {{ max-width: 800px; margin: 2rem auto; padding: 2rem; background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    .alert-error {{ background: #fee2e2; border: 1px solid #ef4444; color: #991b1b; padding: 0.75rem; border-radius: 4px; margin-bottom: 1rem; }}
    .alert-success {{ background: #dcfce7; border: 1px solid #22c55e; color: #166534; padding: 0.75rem; border-radius: 4px; margin-bottom: 1rem; }}
    .form-group {{ margin-bottom: 1rem; }}
    label {{ display: block; font-weight: 600; margin-bottom: 0.25rem; }}
    input[type="text"], input[type="password"], input[type="email"] {{ width: 100%; box-sizing: border-box; padding: 0.5rem; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 1rem; }}
    button {{ background: #2563eb; color: white; border: none; padding: 0.6rem 1.2rem; border-radius: 4px; font-size: 1rem; cursor: pointer; }}
    button:hover {{ background: #1d4ed8; }}
    button:disabled {{ background: #94a3b8; cursor: not-allowed; }}
    .mobile-menu-btn {{ display: none; }}
    @media (max-width: 600px) {{
      .mobile-menu-btn {{ display: block; }}
      nav {{ flex-direction: column; }}
    }}
  </style>
  {js_error_tag}
</head>
<body>
  <header>
    <div><a href="/" style="font-weight: bold; font-size: 1.2rem; color: white; margin-left: 0;">VeriflowApp</a></div>
    <nav id="main-nav">
      <a id="nav-home" href="/">Home</a>
      <a id="nav-dashboard" href="/dashboard">Dashboard</a>
      <a id="nav-items" href="/items">Items</a>
      {auth_link}
    </nav>
  </header>
  <main id="app-root">
    {content}
  </main>
</body>
</html>"""

        # HTML Web Page Routes
        if path == "/":
            content = """
            <h1 id="page-title">Welcome to Veriflow Demo App</h1>
            <p>This deterministic application provides controlled fixtures for browser and journey testing.</p>
            <div id="feature-cards">
              <div class="card">
                <h3>Authentication</h3>
                <p>Test login, registration, password show/hide, and session persistence.</p>
                <a id="cta-login" href="/login">Go to Login &rarr;</a>
              </div>
            </div>
            """
            has_err = (fault == "runtime_error")
            self._send_html(200, layout("Home", content, has_js_error=has_err))

        elif path == "/login":
            return_url = query.get("returnUrl", ["/dashboard"])[0]
            err_msg = query.get("error", [""])[0]
            err_html = f'<div id="login-error" class="alert-error">{err_msg}</div>' if err_msg else ""
            content = f"""
            <h1 id="page-title">Sign In</h1>
            {err_html}
            <form id="login-form" method="POST" action="/login">
              <input type="hidden" name="returnUrl" value="{return_url}">
              <div class="form-group">
                <label for="username">Username</label>
                <input type="text" id="username" name="username" required>
              </div>
              <div class="form-group">
                <label for="password">Password</label>
                <input type="password" id="password" name="password" required>
                <button type="button" id="toggle-password" style="background:#64748b; margin-top:0.25rem; font-size:0.8rem; padding:0.3rem 0.6rem;">Show</button>
              </div>
              <button type="submit" id="submit-login">Sign In</button>
            </form>
            <p style="margin-top: 1rem;">Don't have an account? <a id="link-register" href="/register">Register here</a></p>
            <script>
              document.getElementById('toggle-password').addEventListener('click', function() {{
                var pass = document.getElementById('password');
                if (pass.type === 'password') {{
                  pass.type = 'text';
                  this.textContent = 'Hide';
                }} else {{
                  pass.type = 'password';
                  this.textContent = 'Show';
                }}
              }});
            </script>
            """
            self._send_html(200, layout("Login", content))

        elif path == "/register":
            err_msg = query.get("error", [""])[0]
            err_html = f'<div id="register-error" class="alert-error">{err_msg}</div>' if err_msg else ""
            content = f"""
            <h1 id="page-title">Register an Account</h1>
            {err_html}
            <form id="register-form" method="POST" action="/register">
              <div class="form-group">
                <label for="reg-username">Username</label>
                <input type="text" id="reg-username" name="username" required>
              </div>
              <div class="form-group">
                <label for="reg-email">Email Address</label>
                <input type="email" id="reg-email" name="email" required>
              </div>
              <div class="form-group">
                <label for="reg-password">Password</label>
                <input type="password" id="reg-password" name="password" required>
              </div>
              <button type="submit" id="submit-register">Create Account</button>
            </form>
            """
            self._send_html(200, layout("Register", content))

        elif path == "/dashboard":
            session_user = self._get_cookie("vf_session")
            if not session_user and fault != "broken_auth_guard":
                self._send_html(
                    302,
                    "",
                    extra_headers=[("Location", "/login?returnUrl=%2Fdashboard")],
                )
                return

            user_display = session_user or "Anonymous (Broken Guard)"
            content = f"""
            <h1 id="page-title">User Dashboard</h1>
            <div id="welcome-banner" class="alert-success">Welcome to your secure portal, <span id="auth-username">{user_display}</span>!</div>
            <p id="dashboard-status">Protected route access confirmed.</p>
            <a id="btn-refresh" href="/dashboard">Reload Dashboard</a>
            """
            self._send_html(200, layout("Dashboard", content))

        elif path == "/items":
            content = """
            <h1 id="page-title">Product Catalog</h1>
            <div class="form-group">
              <input type="text" id="search-input" placeholder="Search items...">
            </div>
            <table id="items-table" style="width:100%; border-collapse: collapse;">
              <thead>
                <tr style="border-bottom: 2px solid #cbd5e1;">
                  <th style="text-align:left; padding:0.5rem;">ID</th>
                  <th style="text-align:left; padding:0.5rem;">Name</th>
                  <th style="text-align:left; padding:0.5rem;">Category</th>
                </tr>
              </thead>
              <tbody id="items-body">
                <tr><td style="padding:0.5rem;">1</td><td>Standard Widget</td><td>Tools</td></tr>
                <tr><td style="padding:0.5rem;">2</td><td>Deluxe Gadget</td><td>Electronics</td></tr>
              </tbody>
            </table>
            """
            self._send_html(200, layout("Items", content))

        elif path == "/logout":
            self._send_html(
                302,
                "",
                extra_headers=[
                    ("Location", "/login"),
                    ("Set-Cookie", "vf_session=; Path=/; Expires=Thu, 01 Jan 1970 00:00:00 GMT; HttpOnly"),
                ],
            )

        # RESTful API Endpoints
        elif path in ("/api/health", "/api/ready"):
            self._send_json(200, {
                "status": "ok",
                "service": "veriflow-demo-api",
                "version": "1.0.0",
                "dependencies": {
                    "database": "connected",
                    "cache": "connected",
                },
            })

        elif path == "/api/items":
            if fault == "fault_api_schema":
                # Drops required 'price' field to simulate schema drift
                self._send_json(200, [{"id": 1, "name": "Broken Widget"}])
                return

            items_list = list(self.items_db.values())
            self._send_json(200, items_list)

        elif path.startswith("/api/items/"):
            raw_id = path[len("/api/items/"):]
            try:
                item_id = int(raw_id)
                if item_id in self.items_db:
                    self._send_json(200, self.items_db[item_id])
                else:
                    self._send_json(404, {"error": "Item not found", "code": "NOT_FOUND", "item_id": item_id})
            except ValueError:
                self._send_json(400, {"error": "Invalid item ID format", "code": "INVALID_ID"})

        elif path == "/api/profile":
            auth = self._get_auth_user()
            if not auth and fault != "fault_api_auth_bypass":
                self._send_json(401, {
                    "error": "Authentication required",
                    "code": "UNAUTHORIZED",
                    "hint": "Include 'Authorization: Bearer token_user' header",
                })
                return

            username, role = auth or ("bypassed_user", "user")
            self._send_json(200, {
                "username": username,
                "role": role,
                "email": f"{username}@example.local",
                "active": True,
            })

        elif path == "/api/admin/metrics":
            auth = self._get_auth_user()
            if not auth and fault != "fault_api_auth_bypass" and fault != "fault_api_role_bypass":
                self._send_json(401, {"error": "Authentication required", "code": "UNAUTHORIZED"})
                return

            username, role = auth or ("bypassed_admin", "admin" if fault == "fault_api_role_bypass" else "user")
            if role != "admin" and fault != "fault_api_role_bypass":
                self._send_json(403, {
                    "error": "Forbidden: Administrator role required",
                    "code": "FORBIDDEN",
                })
                return

            self._send_json(200, {
                "system": "veriflow-metrics",
                "active_sessions": 3,
                "requests_per_min": 42,
                "cpu_load_percent": 12.5,
            })

        elif path == "/api/dependency/status":
            if fault == "fault_api_dependency":
                self._send_json(503, {
                    "error": "External payment dependency unavailable",
                    "code": "DEPENDENCY_UNAVAILABLE",
                    "fallback": "offline_queue_active",
                })
                return

            self._send_json(200, {
                "dependency": "payment_service",
                "status": "available",
                "latency_ms": 14.2,
            })

        elif path == "/api/rate-limit-test":
            self._send_json(429, {
                "error": "Too Many Requests",
                "code": "RATE_LIMITED",
                "retry_after": 60,
            }, extra_headers=[("Retry-After", "60")])

        elif path == "/api/faulty/crash":
            if fault == "fault_api_stacktrace":
                # Leaks stack trace and credentials
                body = (
                    "Internal Server Error:\n"
                    "Traceback (most recent call last):\n"
                    "  File \"server.py\", line 120, in do_GET\n"
                    "DatabaseConnectionError: Password=db_super_secret_123 failed for host db.internal"
                ).encode("utf-8")
                self.send_response(500)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            # Clean 500 without stack trace
            self._send_json(500, {
                "error": "An unexpected server error occurred",
                "code": "INTERNAL_SERVER_ERROR",
            })

        elif path == "/api/faulty/malformed":
            # Returns HTML on what should be an API endpoint
            html = "<html><body>502 Bad Gateway - Nginx Proxy Error</body></html>".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html)))
            self.end_headers()
            self.wfile.write(html)

        elif path == "/api/faulty/slow":
            # Sleep to trigger timeout
            time.sleep(3.0)
            self._send_json(200, {"status": "slow_response"})

        elif path == "/api/fail-500":
            self._send_json(500, {"error": "Simulated 500 internal server failure"})

        else:
            if path.startswith("/api/"):
                self._send_json(404, {"error": "API route not found", "code": "NOT_FOUND"})
            else:
                content = """
                <h1 id="page-title">404 — Page Not Found</h1>
                <p id="not-found-msg">The requested URL was not found on this server.</p>
                <a id="back-home-link" href="/">Return to Home</a>
                """
                self._send_html(404, layout("Not Found", content))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        body = self._parse_body()
        fault = self.server_config.get("fault", "")

        if path == "/api/items":
            if not isinstance(body, dict) or body.get("_invalid_json"):
                self._send_json(400, {
                    "error": "Malformed JSON payload",
                    "code": "INVALID_JSON",
                })
                return

            name = str(body.get("name", "")).strip()
            price = body.get("price")
            category = str(body.get("category", "General")).strip()

            # Validation
            validation_errors = []
            if not name:
                validation_errors.append({"field": "name", "message": "Item name is required and cannot be empty."})
            if price is None:
                validation_errors.append({"field": "price", "message": "Price is required."})
            else:
                try:
                    price_val = float(price)
                    if price_val < 0 and fault != "fault_api_missing_validation":
                        validation_errors.append({"field": "price", "message": "Price must be non-negative."})
                    price = price_val
                except (ValueError, TypeError):
                    validation_errors.append({"field": "price", "message": "Price must be a valid number."})

            if validation_errors and fault != "fault_api_missing_validation":
                self._send_json(400, {
                    "error": "Input validation failed",
                    "code": "VALIDATION_ERROR",
                    "details": validation_errors,
                })
                return

            new_id = max(self.items_db.keys(), default=0) + 1
            new_item = {
                "id": new_id,
                "name": name or "Unnamed Item",
                "price": price if price is not None else 0.0,
                "category": category,
            }
            self.items_db[new_id] = new_item
            self._send_json(201, new_item, extra_headers=[("Location", f"/api/items/{new_id}")])

        elif path in ("/api/health", "/api/ready", "/api/profile", "/api/admin/metrics"):
            # Method not allowed for GET-only endpoints
            self._send_json(405, {
                "error": f"Method POST not allowed on {path}",
                "code": "METHOD_NOT_ALLOWED",
            }, extra_headers=[("Allow", "GET")])

        elif path == "/login":
            username = body.get("username", "").strip()
            password = body.get("password", "").strip()
            return_url = body.get("returnUrl", "/dashboard")

            if fault == "faulty_redirect":
                self._send_html(
                    302,
                    "",
                    extra_headers=[
                        ("Location", "/login?error=Faulty+redirect+occurred"),
                        ("Set-Cookie", f"vf_session={username}; Path=/; HttpOnly"),
                    ],
                )
                return

            if username == "admin" and password == "secret123":
                self._send_html(
                    302,
                    "",
                    extra_headers=[
                        ("Location", return_url),
                        ("Set-Cookie", f"vf_session={username}; Path=/; HttpOnly"),
                    ],
                )
            elif username == "nonexistent":
                self._send_html(
                    302,
                    "",
                    extra_headers=[("Location", "/login?error=Account+does+not+exist.+Please+register.")],
                )
            else:
                self._send_html(
                    302,
                    "",
                    extra_headers=[("Location", "/login?error=Invalid+username+or+password")],
                )

        elif path == "/register":
            username = body.get("username", "").strip()
            if username == "existinguser":
                self._send_html(
                    302,
                    "",
                    extra_headers=[("Location", "/register?error=Username+already+taken")],
                )
            else:
                self._send_html(
                    302,
                    "",
                    extra_headers=[
                        ("Location", "/login?success=Account+created+successfully"),
                    ],
                )
        else:
            if path.startswith("/api/"):
                self._send_json(404, {"error": "API route not found", "code": "NOT_FOUND"})
            else:
                self._send_html(404, "Not Found")

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/items/"):
            raw_id = path[len("/api/items/"):]
            try:
                item_id = int(raw_id)
                if item_id in self.items_db:
                    del self.items_db[item_id]
                    self.send_response(204)
                    self.end_headers()
                else:
                    self._send_json(404, {"error": "Item not found", "code": "NOT_FOUND", "item_id": item_id})
            except ValueError:
                self._send_json(400, {"error": "Invalid item ID format", "code": "INVALID_ID"})
        else:
            self._send_json(405, {"error": "Method DELETE not allowed on this path", "code": "METHOD_NOT_ALLOWED"})


class DemoServer:
    """Manager for the Veriflow demo HTTP server."""

    def __init__(self, host: str = "127.0.0.1", port: int = 0, fault: str = ""):
        self.host = host
        self.port = port
        self.fault = fault
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> str:
        self._server = HTTPServer((self.host, self.port), DemoAppHandler)
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
    server = DemoServer(port=8088)
    url = server.start()
    print(f"Veriflow Demo App running at: {url}")
    print("Press Ctrl+C to terminate.")
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        server.stop()
