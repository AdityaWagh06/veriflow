#!/usr/bin/env python3
"""
Veriflow Deterministic Local Demo Web Application.

A lightweight, zero-dependency HTTP server built with Python's standard library.
Provides realistic web pages, form handling, session cookies, route guards,
and controlled fault injection modes for browser automation testing.
"""

from __future__ import annotations

from http import cookies
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import threading
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse


class DemoAppHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Veriflow demo web application."""

    @property
    def server_config(self) -> Dict[str, Any]:
        return getattr(self.server, "server_config", {})

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

    def _parse_body(self) -> Dict[str, str]:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length).decode("utf-8")
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

    def _send_json(self, status: int, data: Dict[str, Any]) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
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

        # Handle Routes
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
            # Route guard check
            if not session_user and fault != "broken_auth_guard":
                # Redirect to login with returnUrl
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

        elif path == "/api/health":
            self._send_json(200, {"status": "ok", "service": "veriflow-demo"})

        elif path == "/api/fail-500":
            self._send_json(500, {"error": "Simulated 500 internal server failure"})

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

        if path == "/login":
            username = body.get("username", "").strip()
            password = body.get("password", "").strip()
            return_url = body.get("returnUrl", "/dashboard")

            if fault == "faulty_redirect":
                # Redirects back to login or nowhere instead of intended destination
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
                # Successful login
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
            self._send_html(404, "Not Found")


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
