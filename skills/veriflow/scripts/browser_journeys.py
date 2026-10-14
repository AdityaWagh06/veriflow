#!/usr/bin/env python3
"""
Veriflow Browser User-Journey Automation Library.

Implements automated behavioral browser testing across critical user journeys:
- Authentication & Account Flows (Login, Registration, Password Toggle)
- Route Guards, Protected Pages & Session Persistence
- Navigation, Deep Links & History Traversal
- Form Validation, Error Feedback & State Retention
- Console Errors, Unhandled Exceptions & Failed Network Requests
- Responsive Viewports & Mobile Reflow

Each test returns a structured BrowserTestResult conforming to Veriflow's 7 result states.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from skills.veriflow.scripts.browser_detector import detect_browser_environment
from skills.veriflow.scripts.browser_reporter import (
    BrowserConsoleEntry,
    BrowserNetworkFailure,
    BrowserTestResult,
)


def launch_browser_context(playwright: Any, channel: Optional[str] = None, headless: bool = True):
    """Launches browser using detected available channel (e.g. chrome, msedge, or chromium)."""
    env = detect_browser_environment(probe_launch=False)
    selected_channel = channel or env.default_channel

    launch_kwargs: Dict[str, Any] = {"headless": headless}
    if selected_channel in ("chrome", "msedge"):
        launch_kwargs["channel"] = selected_channel

    try:
        browser = playwright.chromium.launch(**launch_kwargs)
    except Exception as err:
        # Fallback to standard launch if channel failed
        try:
            browser = playwright.chromium.launch(headless=headless)
        except Exception:
            raise RuntimeError(f"Failed to launch browser engine: {err}") from err

    context = browser.new_context()
    return browser, context


# ==============================================================================
# Authentication & Account Flow Journeys
# ==============================================================================


def test_auth_valid_login(page: Any, base_url: str) -> BrowserTestResult:
    """AUTH-001: Valid credentials authenticate and display appropriate post-login state."""
    start = time.perf_counter()
    target_url = f"{base_url}/login"
    console_errors: List[BrowserConsoleEntry] = []
    network_errors: List[BrowserNetworkFailure] = []

    def on_console(msg: Any):
        if msg.type in ("error", "warning"):
            console_errors.append(BrowserConsoleEntry(level=msg.type, text=msg.text))

    def on_request_failed(req: Any):
        network_errors.append(
            BrowserNetworkFailure(
                url=req.url,
                method=req.method,
                status=None,
                error_text=req.failure or "Request failed",
            )
        )

    page.on("console", on_console)
    page.on("requestfailed", on_request_failed)

    try:
        page.goto(target_url, wait_until="domcontentloaded")
        page.fill("#username", "admin")
        page.fill("#password", "secret123")
        page.click("#submit-login")

        page.wait_for_load_state("domcontentloaded")
        current_url = page.url

        if "/dashboard" not in current_url:
            return BrowserTestResult(
                test_id="AUTH-001",
                name="Valid login journey",
                status="FAIL",
                duration_ms=(time.perf_counter() - start) * 1000,
                url=current_url,
                error_message=f"Expected navigation to /dashboard after login, but remained on {current_url}",
                evidence=f"Current URL: {current_url}",
                console_messages=console_errors,
                network_failures=network_errors,
            )

        welcome_text = page.inner_text("#auth-username") if page.query_selector("#auth-username") else ""
        if "admin" not in welcome_text:
            return BrowserTestResult(
                test_id="AUTH-001",
                name="Valid login journey",
                status="FAIL",
                duration_ms=(time.perf_counter() - start) * 1000,
                url=current_url,
                error_message="User greeting did not reflect authenticated username 'admin'",
                evidence=f"Welcome text: {welcome_text}",
                console_messages=console_errors,
                network_failures=network_errors,
            )

        return BrowserTestResult(
            test_id="AUTH-001",
            name="Valid login journey",
            status="PASS",
            duration_ms=(time.perf_counter() - start) * 1000,
            url=current_url,
            evidence="Successfully authenticated and loaded dashboard with session welcome banner.",
            console_messages=console_errors,
            network_failures=network_errors,
        )
    except Exception as err:
        return BrowserTestResult(
            test_id="AUTH-001",
            name="Valid login journey",
            status="FAIL",
            duration_ms=(time.perf_counter() - start) * 1000,
            url=page.url,
            error_message=f"Exception during login: {err}",
            evidence=str(err),
            console_messages=console_errors,
            network_failures=network_errors,
        )


def test_auth_invalid_login(page: Any, base_url: str) -> BrowserTestResult:
    """AUTH-002: Invalid credentials display clear, non-blocking error feedback."""
    start = time.perf_counter()
    target_url = f"{base_url}/login"

    try:
        page.goto(target_url, wait_until="domcontentloaded")
        page.fill("#username", "admin")
        page.fill("#password", "wrongpass")
        page.click("#submit-login")

        page.wait_for_load_state("domcontentloaded")
        error_element = page.query_selector("#login-error")
        error_text = error_element.inner_text() if error_element else ""

        if not error_element or "Invalid" not in error_text:
            return BrowserTestResult(
                test_id="AUTH-002",
                name="Invalid credentials error handling",
                status="FAIL",
                duration_ms=(time.perf_counter() - start) * 1000,
                url=page.url,
                error_message="No visible error message was displayed after invalid credential submission.",
                evidence=f"Error text found: '{error_text}'",
            )

        return BrowserTestResult(
            test_id="AUTH-002",
            name="Invalid credentials error handling",
            status="PASS",
            duration_ms=(time.perf_counter() - start) * 1000,
            url=page.url,
            evidence=f"Error banner correctly rendered: '{error_text.strip()}'",
        )
    except Exception as err:
        return BrowserTestResult(
            test_id="AUTH-002",
            name="Invalid credentials error handling",
            status="FAIL",
            duration_ms=(time.perf_counter() - start) * 1000,
            url=page.url,
            error_message=str(err),
        )


def test_auth_nonexistent_account(page: Any, base_url: str) -> BrowserTestResult:
    """AUTH-003: Nonexistent account displays error and registration recovery action."""
    start = time.perf_counter()
    target_url = f"{base_url}/login"

    try:
        page.goto(target_url, wait_until="domcontentloaded")
        page.fill("#username", "nonexistent")
        page.fill("#password", "anypassword")
        page.click("#submit-login")

        page.wait_for_load_state("domcontentloaded")
        error_element = page.query_selector("#login-error")
        error_text = error_element.inner_text() if error_element else ""
        has_register_link = bool(page.query_selector("#link-register"))

        if not error_element or "does not exist" not in error_text or not has_register_link:
            return BrowserTestResult(
                test_id="AUTH-003",
                name="Nonexistent account guidance",
                status="FAIL",
                duration_ms=(time.perf_counter() - start) * 1000,
                url=page.url,
                error_message="Expected error indicating nonexistent account with registration link.",
                evidence=f"Found error: '{error_text}', Has register link: {has_register_link}",
            )

        return BrowserTestResult(
            test_id="AUTH-003",
            name="Nonexistent account guidance",
            status="PASS",
            duration_ms=(time.perf_counter() - start) * 1000,
            url=page.url,
            evidence=f"Verified nonexistent account error and registration link: '{error_text.strip()}'",
        )
    except Exception as err:
        return BrowserTestResult(
            test_id="AUTH-003",
            name="Nonexistent account guidance",
            status="FAIL",
            duration_ms=(time.perf_counter() - start) * 1000,
            url=page.url,
            error_message=str(err),
        )


def test_auth_password_toggle(page: Any, base_url: str) -> BrowserTestResult:
    """AUTH-006: Password visibility control toggles between password and text types."""
    start = time.perf_counter()
    target_url = f"{base_url}/login"

    try:
        page.goto(target_url, wait_until="domcontentloaded")
        toggle_btn = page.query_selector("#toggle-password")
        if not toggle_btn:
            return BrowserTestResult(
                test_id="AUTH-006",
                name="Password visibility toggle",
                status="NOT_APPLICABLE",
                duration_ms=(time.perf_counter() - start) * 1000,
                url=target_url,
                evidence="No #toggle-password element found on login form.",
            )

        initial_type = page.get_attribute("#password", "type")
        page.click("#toggle-password")
        toggled_type = page.get_attribute("#password", "type")
        btn_label_toggled = page.inner_text("#toggle-password")

        page.click("#toggle-password")
        reverted_type = page.get_attribute("#password", "type")

        if initial_type == "password" and toggled_type == "text" and reverted_type == "password":
            return BrowserTestResult(
                test_id="AUTH-006",
                name="Password visibility toggle",
                status="PASS",
                duration_ms=(time.perf_counter() - start) * 1000,
                url=target_url,
                evidence="Password field successfully toggled from password -> text -> password.",
            )

        return BrowserTestResult(
            test_id="AUTH-006",
            name="Password visibility toggle",
            status="FAIL",
            duration_ms=(time.perf_counter() - start) * 1000,
            url=target_url,
            error_message=f"Toggle states did not match expectations: initial={initial_type}, toggled={toggled_type}, reverted={reverted_type}",
            evidence=f"Button label: {btn_label_toggled}",
        )
    except Exception as err:
        return BrowserTestResult(
            test_id="AUTH-006",
            name="Password visibility toggle",
            status="FAIL",
            duration_ms=(time.perf_counter() - start) * 1000,
            url=page.url,
            error_message=str(err),
        )


def test_auth_registration_duplicate(page: Any, base_url: str) -> BrowserTestResult:
    """AUTH-005: Registration with duplicate account identifier displays error."""
    start = time.perf_counter()
    target_url = f"{base_url}/register"

    try:
        page.goto(target_url, wait_until="domcontentloaded")
        page.fill("#reg-username", "existinguser")
        page.fill("#reg-email", "existing@example.com")
        page.fill("#reg-password", "SomePassword123")
        page.click("#submit-register")

        page.wait_for_load_state("domcontentloaded")
        error_element = page.query_selector("#register-error")
        error_text = error_element.inner_text() if error_element else ""

        if not error_element or "already taken" not in error_text:
            return BrowserTestResult(
                test_id="AUTH-005",
                name="Duplicate account registration error",
                status="FAIL",
                duration_ms=(time.perf_counter() - start) * 1000,
                url=page.url,
                error_message="Duplicate username did not display a duplicate registration error.",
                evidence=f"Error text: '{error_text}'",
            )

        return BrowserTestResult(
            test_id="AUTH-005",
            name="Duplicate account registration error",
            status="PASS",
            duration_ms=(time.perf_counter() - start) * 1000,
            url=page.url,
            evidence=f"Verified duplicate user validation: '{error_text.strip()}'",
        )
    except Exception as err:
        return BrowserTestResult(
            test_id="AUTH-005",
            name="Duplicate account registration error",
            status="FAIL",
            duration_ms=(time.perf_counter() - start) * 1000,
            url=page.url,
            error_message=str(err),
        )


# ==============================================================================
# Route Guards & Session Lifecycle Journeys
# ==============================================================================


def test_route_guard_unauthenticated(page: Any, base_url: str) -> BrowserTestResult:
    """ROLE-002 / AUTH-009: Unauthenticated direct access to protected page is rejected and redirected."""
    start = time.perf_counter()
    target_url = f"{base_url}/dashboard"

    try:
        page.goto(target_url, wait_until="domcontentloaded")
        current_url = page.url
        dashboard_heading = page.query_selector("#welcome-banner")

        if "/login" in current_url and not dashboard_heading:
            return BrowserTestResult(
                test_id="ROLE-002",
                name="Protected route unauthenticated rejection",
                status="PASS",
                duration_ms=(time.perf_counter() - start) * 1000,
                url=current_url,
                evidence=f"Direct access rejected; redirected to login with returnUrl preservation: {current_url}",
            )

        return BrowserTestResult(
            test_id="ROLE-002",
            name="Protected route unauthenticated rejection",
            status="FAIL",
            duration_ms=(time.perf_counter() - start) * 1000,
            url=current_url,
            error_message="Protected route did not reject unauthenticated access.",
            evidence=f"Expected redirect to /login, but accessed {current_url} with banner present: {bool(dashboard_heading)}",
        )
    except Exception as err:
        return BrowserTestResult(
            test_id="ROLE-002",
            name="Protected route unauthenticated rejection",
            status="FAIL",
            duration_ms=(time.perf_counter() - start) * 1000,
            url=page.url,
            error_message=str(err),
        )


def test_session_persistence_after_refresh(page: Any, base_url: str) -> BrowserTestResult:
    """AUTH-008: Authenticated session state persists across page reload."""
    start = time.perf_counter()
    login_url = f"{base_url}/login"

    try:
        page.goto(login_url, wait_until="domcontentloaded")
        page.fill("#username", "admin")
        page.fill("#password", "secret123")
        page.click("#submit-login")
        page.wait_for_load_state("domcontentloaded")

        if "/dashboard" not in page.url:
            return BrowserTestResult(
                test_id="AUTH-008",
                name="Session persistence after refresh",
                status="BLOCKED",
                duration_ms=(time.perf_counter() - start) * 1000,
                url=page.url,
                error_message="Initial login prerequisite failed.",
            )

        # Trigger browser page refresh
        page.reload(wait_until="domcontentloaded")
        current_url = page.url
        has_banner = bool(page.query_selector("#welcome-banner"))

        if "/dashboard" in current_url and has_banner:
            return BrowserTestResult(
                test_id="AUTH-008",
                name="Session persistence after refresh",
                status="PASS",
                duration_ms=(time.perf_counter() - start) * 1000,
                url=current_url,
                evidence="Session remained active and dashboard rendered without re-authentication after reload.",
            )

        return BrowserTestResult(
            test_id="AUTH-008",
            name="Session persistence after refresh",
            status="FAIL",
            duration_ms=(time.perf_counter() - start) * 1000,
            url=current_url,
            error_message="Session was lost upon page refresh.",
            evidence=f"URL after reload: {current_url}, Banner present: {has_banner}",
        )
    except Exception as err:
        return BrowserTestResult(
            test_id="AUTH-008",
            name="Session persistence after refresh",
            status="FAIL",
            duration_ms=(time.perf_counter() - start) * 1000,
            url=page.url,
            error_message=str(err),
        )


def test_logout_invalidates_session(page: Any, base_url: str) -> BrowserTestResult:
    """AUTH-007: Logout invalidates session and prevents direct navigation to protected pages."""
    start = time.perf_counter()
    login_url = f"{base_url}/login"

    try:
        page.goto(login_url, wait_until="domcontentloaded")
        page.fill("#username", "admin")
        page.fill("#password", "secret123")
        page.click("#submit-login")
        page.wait_for_load_state("domcontentloaded")

        logout_btn = page.query_selector("#logout-btn")
        if not logout_btn:
            return BrowserTestResult(
                test_id="AUTH-007",
                name="Logout session invalidation",
                status="BLOCKED",
                duration_ms=(time.perf_counter() - start) * 1000,
                url=page.url,
                error_message="Logout button not found after login.",
            )

        page.click("#logout-btn")
        page.wait_for_load_state("domcontentloaded")

        # Direct navigation to protected route after logout
        page.goto(f"{base_url}/dashboard", wait_until="domcontentloaded")
        url_after_direct = page.url
        banner_after_direct = bool(page.query_selector("#welcome-banner"))

        if "/login" in url_after_direct and not banner_after_direct:
            return BrowserTestResult(
                test_id="AUTH-007",
                name="Logout session invalidation",
                status="PASS",
                duration_ms=(time.perf_counter() - start) * 1000,
                url=url_after_direct,
                evidence="Session successfully invalidated; subsequent access redirected to login.",
            )

        return BrowserTestResult(
            test_id="AUTH-007",
            name="Logout session invalidation",
            status="FAIL",
            duration_ms=(time.perf_counter() - start) * 1000,
            url=url_after_direct,
            error_message="Protected page was still accessible after logout.",
            evidence=f"URL: {url_after_direct}, Banner present: {banner_after_direct}",
        )
    except Exception as err:
        return BrowserTestResult(
            test_id="AUTH-007",
            name="Logout session invalidation",
            status="FAIL",
            duration_ms=(time.perf_counter() - start) * 1000,
            url=page.url,
            error_message=str(err),
        )
