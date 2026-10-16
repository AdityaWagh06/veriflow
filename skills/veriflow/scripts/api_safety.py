#!/usr/bin/env python3
"""
Veriflow API Target Safety & Safe Request Utility.

Enforces strict safety boundaries for API verification:
- Restricts target requests to local/loopback addresses by default (localhost, 127.0.0.1, ::1).
- Prevents accidental requests to external or production networks.
- Enforces per-request timeouts (default 5.0s).
- Enforces bounded response body capture to prevent memory exhaustion.
- Zero external package dependencies (built on Python's standard library).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import socket
import sys
import time
from typing import Any, Dict, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
import urllib.request

LOCAL_HOSTNAMES = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "[::1]"}
DEFAULT_MAX_BODY_BYTES = 16384  # 16 KB bounded capture
DEFAULT_TIMEOUT_SECONDS = 5.0


class UnsafeTargetError(ValueError):
    """Raised when an API target URL violates safety boundaries."""
    pass


def is_local_target(url_or_host: str) -> bool:
    """Check if the given URL or host resolves to a local/loopback destination."""
    if not url_or_host:
        return False

    parsed = urlparse(url_or_host) if "://" in url_or_host else None
    hostname = (parsed.hostname if parsed else url_or_host) or ""
    hostname = hostname.strip().lower()

    if hostname in LOCAL_HOSTNAMES or hostname.startswith("127."):
        return True

    # Check IPv6 loopback
    if hostname in ("::1", "[::1]"):
        return True

    # Attempt to resolve hostname to IP and check for loopback
    try:
        addrinfo = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        for family, _, _, _, sockaddr in addrinfo:
            ip = sockaddr[0]
            if ip.startswith("127.") or ip == "::1" or ip == "0.0.0.0":
                return True
    except (socket.gaierror, OSError):
        pass

    return False


def validate_target_url(url: str, allow_external: bool = False) -> str:
    """Validate that a target URL has a valid scheme and complies with safety policies.

    Args:
        url: The candidate URL string (e.g. http://127.0.0.1:8000/api/health).
        allow_external: If False (default), raises UnsafeTargetError for non-local targets.

    Returns:
        The normalized target URL string.

    Raises:
        UnsafeTargetError: If scheme is unsupported or destination is an unauthorized external host.
    """
    if not url or not isinstance(url, str):
        raise UnsafeTargetError("Target URL must be a non-empty string.")

    url = url.strip()
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        raise UnsafeTargetError(f"Unsupported URL scheme '{parsed.scheme}'. Only http and https are allowed.")

    if not parsed.netloc:
        raise UnsafeTargetError(f"Target URL '{url}' is missing hostname or port.")

    if not allow_external and not is_local_target(url):
        raise UnsafeTargetError(
            f"Target host '{parsed.hostname}' is not a local/loopback address. "
            "Veriflow prohibits requests to external or production destinations without explicit authorization."
        )

    return url


@dataclass
class SafeHttpResponse:
    """Structured representation of a safe HTTP request outcome."""

    status: int
    headers: Dict[str, str] = field(default_factory=dict)
    body_bytes: bytes = b""
    body_text: str = ""
    duration_ms: float = 0.0
    error: Optional[str] = None
    is_timeout: bool = False
    url: str = ""
    method: str = "GET"

    @property
    def is_json(self) -> bool:
        content_type = self.headers.get("content-type", "").lower()
        return "application/json" in content_type

    def json(self) -> Any:
        """Parse body as JSON. Raises ValueError if body is not valid JSON."""
        return json.loads(self.body_text)


def safe_http_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    body: Optional[bytes | str] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES,
    allow_external: bool = False,
) -> SafeHttpResponse:
    """Safely executes an HTTP request within bounded limits.

    - Validates target safety (local-only unless allow_external is True).
    - Enforces timeout.
    - Captures at most max_body_bytes.
    - Handles standard HTTP errors (4xx, 5xx) as valid structured responses rather than unhandled exceptions.
    """
    start_time = time.perf_counter()
    normalized_url = validate_target_url(url, allow_external=allow_external)
    req_headers = dict(headers or {})

    # Ensure method is uppercase
    method = method.upper()

    # Prepare body
    encoded_body: Optional[bytes] = None
    if body is not None:
        if isinstance(body, str):
            encoded_body = body.encode("utf-8")
        else:
            encoded_body = body
        if "Content-Length" not in req_headers and "content-length" not in req_headers:
            req_headers["Content-Length"] = str(len(encoded_body))

    req = urllib.request.Request(
        url=normalized_url,
        data=encoded_body,
        headers=req_headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            resp_headers = {k.lower(): v for k, v in resp.headers.items()}
            raw_bytes = resp.read(max_body_bytes)
            text = raw_bytes.decode("utf-8", errors="replace")
            return SafeHttpResponse(
                status=resp.status,
                headers=resp_headers,
                body_bytes=raw_bytes,
                body_text=text,
                duration_ms=round(elapsed_ms, 2),
                url=normalized_url,
                method=method,
            )
    except HTTPError as http_err:
        # HTTPError is also a valid response representation for 4xx/5xx
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        resp_headers = {k.lower(): v for k, v in http_err.headers.items()}
        raw_bytes = http_err.read(max_body_bytes)
        text = raw_bytes.decode("utf-8", errors="replace")
        return SafeHttpResponse(
            status=http_err.code,
            headers=resp_headers,
            body_bytes=raw_bytes,
            body_text=text,
            duration_ms=round(elapsed_ms, 2),
            error=f"HTTP {http_err.code}: {http_err.reason}",
            url=normalized_url,
            method=method,
        )
    except (socket.timeout, TimeoutError) as timeout_err:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return SafeHttpResponse(
            status=0,
            duration_ms=round(elapsed_ms, 2),
            error=f"Request timed out after {timeout:.1f}s",
            is_timeout=True,
            url=normalized_url,
            method=method,
        )
    except URLError as url_err:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        reason_str = str(url_err.reason)
        is_timed_out = "timed out" in reason_str.lower()
        return SafeHttpResponse(
            status=0,
            duration_ms=round(elapsed_ms, 2),
            error=f"Connection failed: {reason_str}",
            is_timeout=is_timed_out,
            url=normalized_url,
            method=method,
        )
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return SafeHttpResponse(
            status=0,
            duration_ms=round(elapsed_ms, 2),
            error=f"Execution error: {exc}",
            url=normalized_url,
            method=method,
        )
