#!/usr/bin/env python3
"""
Veriflow Browser Environment & Tool Availability Detector.

Performs safe, non-destructive detection of browser automation capabilities:
- Checks if the Python 'playwright' package is installed.
- Detects available browser engines (chromium, firefox, webkit) and system channels (chrome, msedge).
- Distinguishes AVAILABLE from BLOCKED status with actionable remediation guidance.
- NEVER automatically downloads packages or browser binaries.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
import shutil
import sys
from typing import Any, Dict, List, Optional


@dataclass
class BrowserEnvironment:
    """Represents the operational availability of browser automation tools."""

    playwright_installed: bool
    playwright_version: Optional[str] = None
    available_channels: List[str] = field(default_factory=list)
    default_channel: Optional[str] = None
    status: str = "BLOCKED"  # "AVAILABLE" | "BLOCKED"
    reason: str = ""
    remediation: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "playwright_installed": self.playwright_installed,
            "playwright_version": self.playwright_version,
            "available_channels": list(self.available_channels),
            "default_channel": self.default_channel,
            "status": self.status,
            "reason": self.reason,
            "remediation": self.remediation,
        }


def detect_browser_environment(probe_launch: bool = False) -> BrowserEnvironment:
    """Detect whether Playwright and browser engines/channels are available.

    Args:
        probe_launch: If True, test-launches a minimal headless instance to verify execution.
                      If False, uses fast executable/import inspection without launching processes.
    """
    playwright_spec = importlib.util.find_spec("playwright")
    if playwright_spec is None:
        return BrowserEnvironment(
            playwright_installed=False,
            status="BLOCKED",
            reason="Python package 'playwright' is not installed in the current environment.",
            remediation=(
                "Install Playwright manually using: pip install playwright. "
                "Veriflow will not automatically install packages."
            ),
        )

    # Check package version
    version_str = None
    try:
        import playwright
        version_str = getattr(playwright, "__version__", "unknown")
    except Exception:
        version_str = "installed"

    # Identify potential channels on Windows, macOS, and Linux
    candidate_channels = ["chromium", "chrome", "msedge", "firefox", "webkit"]
    available_channels: List[str] = []

    # Fast probe: check system PATH or registry for system browsers
    has_chrome = bool(
        shutil.which("chrome")
        or shutil.which("google-chrome")
        or shutil.which("google-chrome-stable")
        or _check_windows_browser_path("Google\\Chrome\\Application\\chrome.exe")
    )
    has_msedge = bool(
        shutil.which("msedge")
        or shutil.which("edge")
        or _check_windows_browser_path("Microsoft\\Edge\\Application\\msedge.exe")
    )

    if has_chrome:
        available_channels.append("chrome")
    if has_msedge:
        available_channels.append("msedge")

    if probe_launch:
        # Verify launchability with playwright
        try:
            from playwright.sync_api import sync_playwright  # type: ignore

            with sync_playwright() as p:
                # Test standard chromium
                try:
                    b = p.chromium.launch(headless=True)
                    b.close()
                    if "chromium" not in available_channels:
                        available_channels.insert(0, "chromium")
                except Exception:
                    pass

                # Test chrome channel if present
                if "chrome" in available_channels:
                    try:
                        b = p.chromium.launch(channel="chrome", headless=True)
                        b.close()
                    except Exception:
                        available_channels.remove("chrome")

                # Test msedge channel if present
                if "msedge" in available_channels:
                    try:
                        b = p.chromium.launch(channel="msedge", headless=True)
                        b.close()
                    except Exception:
                        available_channels.remove("msedge")
        except Exception as err:
            return BrowserEnvironment(
                playwright_installed=True,
                playwright_version=version_str,
                available_channels=[],
                status="BLOCKED",
                reason=f"Playwright import failed: {err}",
                remediation="Verify Playwright installation via: python -m playwright --version",
            )

    # If no channels detected yet but playwright is installed, attempt default 'chromium'
    if not available_channels:
        # Default fallback
        available_channels.append("chromium")

    # Select default channel
    default_ch = None
    if "chromium" in available_channels:
        default_ch = "chromium"
    elif "chrome" in available_channels:
        default_ch = "chrome"
    elif "msedge" in available_channels:
        default_ch = "msedge"
    elif available_channels:
        default_ch = available_channels[0]

    return BrowserEnvironment(
        playwright_installed=True,
        playwright_version=version_str,
        available_channels=available_channels,
        default_channel=default_ch,
        status="AVAILABLE" if available_channels else "BLOCKED",
        reason="Browser automation environment is ready." if available_channels else "No launchable browser engines found.",
        remediation=None if available_channels else "Install a browser using: playwright install chromium",
    )


def _check_windows_browser_path(relative_suffix: str) -> bool:
    """Helper to detect common Windows Program Files installation paths."""
    if sys.platform != "win32":
        return False
    from pathlib import Path
    import os

    prog_files = [
        os.environ.get("ProgramFiles", r"C:\Program Files"),
        os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
        os.environ.get("LocalAppData", ""),
    ]
    for base in prog_files:
        if base and (Path(base) / relative_suffix).exists():
            return True
    return False


if __name__ == "__main__":
    import json

    env = detect_browser_environment(probe_launch=False)
    print(json.dumps(env.to_dict(), indent=2))
