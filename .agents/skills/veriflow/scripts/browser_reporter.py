#!/usr/bin/env python3
"""
Veriflow Browser Test Result Schema and Diagnostic Reporter.

Standardizes browser automation outcomes into Veriflow's 7 explicit result states:
PASS, FAIL, BLOCKED, NOT_RUN, NOT_APPLICABLE, MANUAL_REVIEW, UNKNOWN.

Enforces privacy and credential safety:
- Redacts password parameters, session tokens, authorization headers, and cookies.
- Captures console errors, network failures, and diagnostic traces.
- Produces clean human-readable and structured JSON reports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import re
from typing import Any, Dict, List, Optional

VALID_STATUSES = {
    "PASS",
    "FAIL",
    "BLOCKED",
    "NOT_RUN",
    "NOT_APPLICABLE",
    "MANUAL_REVIEW",
    "UNKNOWN",
}

# Patterns for redacting sensitive values
_SENSITIVE_PATTERNS = [
    (re.compile(r'(password|pass|passwd|secret|token|auth|key)=([^\s&]+)', re.IGNORECASE), r'\1=[REDACTED]'),
    (re.compile(r'(Bearer\s+)[A-Za-z0-9\-\._~\+\/]+=*', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(set-cookie:\s*)([^\r\n]+)', re.IGNORECASE), r'\1[REDACTED]'),
]


def redact_sensitive_data(text: str) -> str:
    """Sanitizes text by masking credentials, passwords, and authorization tokens."""
    if not text:
        return text
    sanitized = text
    for pattern, replacement in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


@dataclass
class BrowserConsoleEntry:
    level: str  # "error", "warning", "info", "log"
    text: str
    location: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "level": self.level,
            "text": redact_sensitive_data(self.text),
            "location": self.location,
        }


@dataclass
class BrowserNetworkFailure:
    url: str
    method: str
    status: Optional[int]
    error_text: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": redact_sensitive_data(self.url),
            "method": self.method,
            "status": self.status,
            "error_text": redact_sensitive_data(self.error_text),
        }


@dataclass
class BrowserTestResult:
    test_id: str
    name: str
    status: str
    duration_ms: float = 0.0
    url: Optional[str] = None
    error_message: Optional[str] = None
    evidence: Optional[str] = None
    remediation: Optional[str] = None
    console_messages: List[BrowserConsoleEntry] = field(default_factory=list)
    network_failures: List[BrowserNetworkFailure] = field(default_factory=list)
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{self.status}'. Must be one of {sorted(VALID_STATUSES)}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "name": self.name,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 2),
            "url": redact_sensitive_data(self.url or ""),
            "error_message": redact_sensitive_data(self.error_message or "") if self.error_message else None,
            "evidence": redact_sensitive_data(self.evidence or "") if self.evidence else None,
            "remediation": self.remediation,
            "console_messages": [c.to_dict() for c in self.console_messages],
            "network_failures": [n.to_dict() for n in self.network_failures],
            "diagnostics": self.diagnostics,
        }


@dataclass
class BrowserExecutionReport:
    target_url: str
    browser_channel: str
    results: List[BrowserTestResult] = field(default_factory=list)
    environment_info: Optional[Dict[str, Any]] = None

    def add_result(self, result: BrowserTestResult) -> None:
        self.results.append(result)

    def summary_counts(self) -> Dict[str, int]:
        counts = {s: 0 for s in sorted(VALID_STATUSES)}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_url": redact_sensitive_data(self.target_url),
            "browser_channel": self.browser_channel,
            "summary": self.summary_counts(),
            "total_tests": len(self.results),
            "results": [r.to_dict() for r in self.results],
            "environment_info": self.environment_info,
        }

    def format_text(self) -> str:
        counts = self.summary_counts()
        lines = [
            "=" * 60,
            "Veriflow Browser Verification Report",
            "=" * 60,
            f"Target URL:       {redact_sensitive_data(self.target_url)}",
            f"Browser Channel:  {self.browser_channel}",
            f"Total Tests:      {len(self.results)}",
            (
                f"Summary: PASS={counts['PASS']} | FAIL={counts['FAIL']} | "
                f"BLOCKED={counts['BLOCKED']} | NOT_RUN={counts['NOT_RUN']} | "
                f"NOT_APPLICABLE={counts['NOT_APPLICABLE']} | "
                f"MANUAL_REVIEW={counts['MANUAL_REVIEW']} | UNKNOWN={counts['UNKNOWN']}"
            ),
            "-" * 60,
        ]

        for r in self.results:
            duration_str = f"({r.duration_ms:.1f}ms)"
            lines.append(f"[{r.status:^8}] {r.test_id}: {r.name} {duration_str}")
            if r.error_message:
                lines.append(f"           Error: {redact_sensitive_data(r.error_message)}")
            if r.evidence:
                lines.append(f"           Evidence: {redact_sensitive_data(r.evidence)}")
            if r.network_failures:
                lines.append(f"           Network Failures ({len(r.network_failures)}):")
                for nf in r.network_failures[:3]:
                    lines.append(f"             - [{nf.status or 'ERR'}] {nf.method} {redact_sensitive_data(nf.url)}")
            if r.console_messages:
                error_consoles = [c for c in r.console_messages if c.level in ("error", "warning")]
                if error_consoles:
                    lines.append(f"           Console Errors/Warnings ({len(error_consoles)}):")
                    for ce in error_consoles[:3]:
                        lines.append(f"             - [{ce.level.upper()}] {redact_sensitive_data(ce.text)}")

        lines.extend([
            "-" * 60,
            "Safety Notice: Results reflect executed browser assertions. Passing tests do not",
            "guarantee zero defects under untested conditions.",
            "=" * 60,
        ])
        return "\n".join(lines)
