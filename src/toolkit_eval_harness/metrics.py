"""Lightweight metrics collection for toolkit-eval-harness.

Provides simple counters, timers, and gauge tracking without external
dependencies.  Designed for CLI-tool use -- all state lives in-process
and can be serialised to a plain dict for inclusion in reports.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TimerResult:
    """Result of a completed timer measurement."""

    name: str
    elapsed_seconds: float


class MetricsCollector:
    """Thread-safe, in-process metrics collector.

    Tracks three metric types:

    * **counters** -- monotonically increasing integers (e.g. test counts).
    * **timers** -- elapsed-time measurements stored as lists of floats.
    * **gauges** -- point-in-time numeric values (e.g. score averages).

    Usage::

        mc = MetricsCollector()
        mc.increment("tests.passed")
        mc.set_gauge("score.avg", 0.85)

        with mc.timer("suite.run"):
            run_suite(...)

        snapshot = mc.snapshot()
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {}
        self._timers: dict[str, list[float]] = {}
        self._gauges: dict[str, float] = {}

    # -- counters -------------------------------------------------------------

    def increment(self, name: str, delta: int = 1) -> int:
        """Increment a counter by *delta* (default 1) and return its new value."""
        with self._lock:
            self._counters[name] = self._counters.get(name, 0) + delta
            value = self._counters[name]
        logger.debug("metrics.counter %s = %d (+%d)", name, value, delta)
        return value

    def get_counter(self, name: str) -> int:
        """Return current value of a counter (0 if not set)."""
        with self._lock:
            return self._counters.get(name, 0)

    # -- timers ---------------------------------------------------------------

    def timer(self, name: str) -> _TimerContext:
        """Return a context manager that records elapsed time under *name*."""
        return _TimerContext(collector=self, name=name)

    def record_time(self, name: str, elapsed: float) -> None:
        """Manually record an elapsed-time measurement."""
        with self._lock:
            self._timers.setdefault(name, []).append(elapsed)
        logger.debug("metrics.timer %s = %.4fs", name, elapsed)

    def get_timer(self, name: str) -> list[float]:
        """Return all recorded durations for *name*."""
        with self._lock:
            return list(self._timers.get(name, []))

    # -- gauges ---------------------------------------------------------------

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge to an absolute value."""
        with self._lock:
            self._gauges[name] = value
        logger.debug("metrics.gauge %s = %.4f", name, value)

    def get_gauge(self, name: str) -> float | None:
        """Return the current gauge value, or ``None`` if unset."""
        with self._lock:
            return self._gauges.get(name)

    # -- snapshot -------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serialisable snapshot of all metrics."""
        with self._lock:
            timers_summary: dict[str, dict[str, Any]] = {}
            for name, values in self._timers.items():
                timers_summary[name] = {
                    "count": len(values),
                    "total_seconds": round(sum(values), 6),
                    "min_seconds": round(min(values), 6) if values else 0.0,
                    "max_seconds": round(max(values), 6) if values else 0.0,
                }
            return {
                "counters": dict(self._counters),
                "timers": timers_summary,
                "gauges": {k: round(v, 6) for k, v in self._gauges.items()},
            }

    def reset(self) -> None:
        """Clear all metrics."""
        with self._lock:
            self._counters.clear()
            self._timers.clear()
            self._gauges.clear()
        logger.debug("metrics: all metrics reset")


class _TimerContext:
    """Context manager for timing a block of code."""

    def __init__(self, collector: MetricsCollector, name: str) -> None:
        self._collector = collector
        self._name = name
        self._start: float = 0.0

    def __enter__(self) -> _TimerContext:
        self._start = time.monotonic()
        return self

    def __exit__(self, *exc: object) -> None:
        elapsed = time.monotonic() - self._start
        self._collector.record_time(self._name, elapsed)

    @property
    def elapsed(self) -> float:
        """Elapsed time since entering the context (live reading)."""
        return time.monotonic() - self._start


@dataclass
class SuiteMetrics:
    """Aggregated metrics for a single suite execution.

    This is a convenience wrapper over ``MetricsCollector`` that exposes
    domain-specific fields (pass/fail/skip counts, score, timing).
    """

    total_cases: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    score_sum: float = 0.0
    execution_time_seconds: float = 0.0
    case_times: list[float] = field(default_factory=list)

    @property
    def average_score(self) -> float:
        """Return average score across all cases."""
        return (self.score_sum / self.total_cases) if self.total_cases else 0.0

    def record_case(self, *, score: float, elapsed: float = 0.0, skipped: bool = False) -> None:
        """Record the result of a single test case."""
        self.total_cases += 1
        self.score_sum += score
        self.case_times.append(elapsed)
        if skipped:
            self.skipped += 1
        elif score >= 1.0:
            self.passed += 1
        else:
            self.failed += 1

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable summary."""
        return {
            "total_cases": self.total_cases,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "average_score": round(self.average_score, 6),
            "execution_time_seconds": round(self.execution_time_seconds, 4),
        }
