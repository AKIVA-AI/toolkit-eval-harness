"""Health check utilities for toolkit-eval-harness.

Provides a ``check_health()`` function that validates the runtime
environment and returns a structured report.  This is the programmatic
equivalent of ``toolkit-eval check-deps`` but richer: it validates
importability of internal modules, Python version, optional
dependencies, and basic I/O capability.
"""

from __future__ import annotations

import logging
import platform
import sys
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _check_python_version() -> dict[str, Any]:
    """Verify Python >= 3.10."""
    version = platform.python_version()
    ok = sys.version_info >= (3, 10)
    return {"name": "python_version", "version": version, "ok": ok}


def _check_internal_imports() -> dict[str, Any]:
    """Verify that all internal modules can be imported."""
    modules = [
        "toolkit_eval_harness.runner",
        "toolkit_eval_harness.scoring",
        "toolkit_eval_harness.suite",
        "toolkit_eval_harness.report",
        "toolkit_eval_harness.pack",
        "toolkit_eval_harness.plugins",
        "toolkit_eval_harness.logging_config",
        "toolkit_eval_harness.metrics",
    ]
    failed: list[str] = []
    for mod in modules:
        try:
            __import__(mod)
        except ImportError:
            failed.append(mod)

    ok = len(failed) == 0
    result: dict[str, Any] = {"name": "internal_imports", "ok": ok}
    if failed:
        result["failed_modules"] = failed
    return result


def _check_temp_io() -> dict[str, Any]:
    """Verify that temp directory I/O works (needed for pack extraction)."""
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=True) as f:
            f.write('{"test": true}')
            f.flush()
            # Verify the file exists and is readable
            p = Path(f.name)
            if not p.exists():
                return {"name": "temp_io", "ok": False, "reason": "temp_file_not_found"}
        return {"name": "temp_io", "ok": True}
    except OSError as e:
        return {"name": "temp_io", "ok": False, "reason": str(e)}


def _check_signing_dependency() -> dict[str, Any]:
    """Check availability of optional cryptography package."""
    try:
        import cryptography  # noqa: F401

        version = getattr(cryptography, "__version__", "unknown")
        return {
            "name": "cryptography",
            "ok": True,
            "version": version,
            "optional": True,
        }
    except ImportError:
        return {
            "name": "cryptography",
            "ok": False,
            "optional": True,
            "note": "Install with: pip install 'toolkit-eval-harness[signing]'",
        }


def check_health() -> dict[str, Any]:
    """Run all health checks and return a structured report.

    Returns:
        A dict with keys:

        - ``healthy`` (bool): True if all required checks pass.
        - ``checks`` (list[dict]): Individual check results.
        - ``platform`` (dict): Runtime platform info.

    Example::

        result = check_health()
        if not result["healthy"]:
            for check in result["checks"]:
                if not check["ok"]:
                    print(f"FAIL: {check['name']}")
    """
    logger.info("Running health checks")

    checks = [
        _check_python_version(),
        _check_internal_imports(),
        _check_temp_io(),
        _check_signing_dependency(),
    ]

    # healthy = all required (non-optional) checks pass
    required_ok = all(c["ok"] for c in checks if not c.get("optional", False))

    result: dict[str, Any] = {
        "healthy": required_ok,
        "checks": checks,
        "platform": {
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "architecture": platform.machine(),
        },
    }

    if required_ok:
        logger.info("Health check passed: all required checks OK")
    else:
        failed_names = [c["name"] for c in checks if not c["ok"] and not c.get("optional")]
        logger.warning("Health check FAILED: %s", ", ".join(failed_names))

    return result
