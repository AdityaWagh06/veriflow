#!/usr/bin/env python3
"""
Veriflow API Test Result Schema and Diagnostic Reporter.

Standardizes API & integration verification outcomes into Veriflow's 7 explicit result states:
PASS, FAIL, BLOCKED, NOT_RUN, NOT_APPLICABLE, MANUAL_REVIEW, UNKNOWN.

Enforces privacy and credential safety:
- Redacts authorization headers (Bearer, Basic, API keys).
- Redacts session cookies and sensitive query string parameters.
- Masks sensitive JSON properties (password, token, secret, apiKey).
- Produces clean human-readable summaries and structured JSON reports.
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

_SENSITIVE_PATTERNS = [
    # Authorization header tokens
    (re.compile(r'(Bearer\s+)[A-Za-z0-9\-\._~\+\/]+=*', re.IGNORECASE), r'\1[REDACTED]'),
    (re.compile(r'(Basic\s+)[A-Za-z0-9\-\._~\+\/]+=*', re.IGNORECASE), r'\1[REDACTED]'),
    # Query parameters and URL-encoded form data
    (re.compile(r'((?:api[_-]?key|access[_-]?token|token|password|passwd|secret|auth|client_secret)=)([^&\s\r\n"\'`]+)', re.IGNORECASE), r'\1[REDACTED]'),
    # Cookie headers
    (re.compile(r'((?:set-cookie|cookie):\s*[^=\r\n]+?=)([^;\r\n]+)', re.IGNORECASE), r'\1[REDACTED]'),
    # JSON sensitive field masking. No \b or exact-name anchor: a prefixed key
    # such as "stripe_api_key" or "db_password" must be masked too, and an
    # underscore is a word character so a boundary would exclude it.
    (re.compile(r'("[A-Za-z0-9_\-]*(?:password|passwd|token|secret|apikey|api_key|credential)[A-Za-z0-9_\-]*"\s*:\s*")([^"]*)(")', re.IGNORECASE), r'\1[REDACTED]\3'),
    # Credentials embedded in a connection or request URL. Previously uncovered:
    # a password leaked inside a traceback or error body survived redaction.
    (re.compile(r'(?i)\b((?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|amqp|mssql|ftp|https?)://[^\s:/@\'"]+:)([^\s/@\'"]{3,})(@)'), r'\1[REDACTED]\3'),
    # Well-known provider key prefixes, which carry no surrounding key name.
    (re.compile(r'\b((?:sk_live_|sk_test_|rk_live_|xoxb-|xoxp-|ghp_|gho_|github_pat_|AIza))[A-Za-z0-9_\-]{10,}'), r'\1[REDACTED]'),
    # key: value form (YAML, headers, .env dumps and log lines).
    (re.compile(r'(?im)^(\s*[A-Za-z0-9_\-]*(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token|client_secret)[A-Za-z0-9_\-]*\s*[:=]\s*)(\S{4,})$', re.IGNORECASE), r'\1[REDACTED]'),
]


def redact_api_data(text: str) -> str:
    """Sanitizes text by masking credentials, passwords, tokens, and authorization data."""
    if not text:
        return text
    sanitized = text
    for pattern, replacement in _SENSITIVE_PATTERNS:
        sanitized = pattern.sub(replacement, sanitized)
    return sanitized


def redact_headers(headers: Dict[str, str]) -> Dict[str, str]:
    """Return a copy of headers with sensitive authorization and cookie values masked."""
    sanitized: Dict[str, str] = {}
    for k, v in headers.items():
        k_lower = k.lower()
        if k_lower in ("authorization", "proxy-authorization", "cookie", "set-cookie", "x-api-key"):
            sanitized[k] = "[REDACTED]"
        else:
            sanitized[k] = redact_api_data(v)
    return sanitized


@dataclass
class ApiTestResult:
    """Standardized representation of a single API verification check."""

    test_id: str
    name: str
    status: str
    duration_ms: float = 0.0
    url: Optional[str] = None
    method: str = "GET"
    status_code: Optional[int] = None
    error_message: Optional[str] = None
    evidence: Optional[str] = None
    remediation: Optional[str] = None
    diagnostics: List[Dict[str, Any]] = field(default_factory=list)
    response_body_snippet: Optional[str] = None

    def __post_init__(self):
        if self.status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{self.status}'. Must be one of {sorted(VALID_STATUSES)}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "test_id": self.test_id,
            "name": self.name,
            "status": self.status,
            "duration_ms": round(self.duration_ms, 2),
            "url": redact_api_data(self.url or ""),
            "method": self.method,
            "status_code": self.status_code,
            "error_message": redact_api_data(self.error_message or "") if self.error_message else None,
            "evidence": redact_api_data(self.evidence or "") if self.evidence else None,
            "remediation": self.remediation,
            "diagnostics": self.diagnostics,
            "response_body_snippet": redact_api_data(self.response_body_snippet or "") if self.response_body_snippet else None,
        }


@dataclass
class ApiExecutionReport:
    """Aggregate report for API & integration verification runs."""

    target_url: str
    results: List[ApiTestResult] = field(default_factory=list)
    environment_info: Optional[Dict[str, Any]] = None

    def add_result(self, result: ApiTestResult) -> None:
        self.results.append(result)

    def summary_counts(self) -> Dict[str, int]:
        counts = {s: 0 for s in sorted(VALID_STATUSES)}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_url": redact_api_data(self.target_url),
            "summary": self.summary_counts(),
            "total_tests": len(self.results),
            "results": [r.to_dict() for r in self.results],
            "environment_info": self.environment_info,
        }

    def format_text(self) -> str:
        counts = self.summary_counts()
        lines = [
            "=" * 60,
            "Veriflow API & Integration Verification Report",
            "=" * 60,
            f"Target URL:  {redact_api_data(self.target_url)}",
            f"Total Tests: {len(self.results)}",
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
            code_str = f"[{r.status_code}]" if r.status_code else ""
            lines.append(f"[{r.status:^8}] {r.test_id}: {r.name} {code_str} {duration_str}")
            if r.error_message:
                lines.append(f"           Error: {redact_api_data(r.error_message)}")
            if r.evidence:
                lines.append(f"           Evidence: {redact_api_data(r.evidence)}")
            if r.remediation:
                lines.append(f"           Remediation: {r.remediation}")

        lines.extend([
            "-" * 60,
            "Safety Notice: Results reflect executed API checks under test conditions.",
            "Passing checks do not guarantee zero defects, complete security, or scalability.",
            "=" * 60,
        ])
        return "\n".join(lines)
