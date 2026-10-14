"""
Pytest configuration for Veriflow test suite.
Ensures repository root is present on sys.path for test collection and execution,
and prevents collecting imported library functions as test items.
"""

import inspect
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def pytest_pycollect_makeitem(collector, name, obj):
    """Prevent pytest from collecting functions imported from library modules."""
    if inspect.isfunction(obj):
        mod = getattr(collector, "module", None)
        if mod and getattr(obj, "__module__", None) != mod.__name__:
            return []
    return None
