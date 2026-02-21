from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .compare import CompareBudget, compare_reports
from .pack import create_pack, extract_pack, load_suite_from_path
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
    "__version__",
    "compare_reports",
    "create_pack",
    "extract_pack",
    "load_suite_from_path",
    "run_suite",
]

