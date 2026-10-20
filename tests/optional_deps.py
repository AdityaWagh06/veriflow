"""
Shared guards for Veriflow's optional third-party dependencies.

Veriflow's engines are pure standard library. Two capabilities are optional:
`playwright` (browser journeys) and `PyYAML` (YAML OpenAPI specifications).

A missing optional dependency is a BLOCKED precondition, never a failure. These
helpers let tests skip with an actionable reason instead of reporting a defect in
Veriflow, which would turn an unavailable environment into a false red result.
"""

from __future__ import annotations

import importlib.util
import unittest

PYYAML_REMEDIATION = (
    "Install PyYAML manually using: pip install pyyaml "
    "(or: pip install -r requirements-dev.txt). "
    "Veriflow will not automatically install packages."
)


def pyyaml_installed() -> bool:
    """Return True when PyYAML can be imported in the current environment."""
    return importlib.util.find_spec("yaml") is not None


def require_pyyaml() -> None:
    """Skip the calling test when PyYAML is unavailable.

    Raises:
        unittest.SkipTest: when PyYAML is not installed.
    """
    if not pyyaml_installed():
        raise unittest.SkipTest(
            f"YAML specification support not available: PyYAML is not installed. {PYYAML_REMEDIATION}"
        )
