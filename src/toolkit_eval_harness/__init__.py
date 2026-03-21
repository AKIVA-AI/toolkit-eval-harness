from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .compare import CompareBudget, compare_reports
from .health import check_health
from .metrics import MetricsCollector, SuiteMetrics
from .pack import create_pack, extract_pack, load_suite_from_path
from .plugins import get_scorer, list_scorers, register_scorer, unregister_scorer
from .report import EvalReport
from .runner import run_suite
from .suite import EvalCase, EvalSuite

try:
    __version__ = version("toolkit-eval-harness")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "0.0.0"

__all__ = [
    "CompareBudget",
    "EvalCase",
    "EvalReport",
    "EvalSuite",
    "MetricsCollector",
    "SuiteMetrics",
    "__version__",
    "check_health",
    "compare_reports",
    "create_pack",
    "extract_pack",
    "get_scorer",
    "list_scorers",
    "load_suite_from_path",
    "register_scorer",
    "run_suite",
    "unregister_scorer",
]
