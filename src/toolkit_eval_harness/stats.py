"""Seeded paired bootstrap for score deltas (standard library only).

The percentile bootstrap (Efron and Tibshirani, *An Introduction to the Bootstrap*, 1993,
ch. 13) resamples the per-case deltas ``candidate - baseline`` with replacement, recomputes
the mean each time, and takes the ``(1 - confidence) / 2`` and ``(1 + confidence) / 2``
quantiles of those means. Resampling the deltas resamples the (baseline, candidate) pairs
jointly, which is what makes it a *paired* bootstrap.

Quantiles use linear interpolation between order statistics (NumPy's default ``linear``
method, Hyndman and Fan type 7), which is also what ``scipy.stats.bootstrap`` uses for
``method="percentile"``. ``tests/test_compare_stats.py`` checks the result against
``scipy.stats.bootstrap(..., paired=True, method="percentile")``.
"""

from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import dataclass

DEFAULT_ITERATIONS = 10_000
DEFAULT_CONFIDENCE = 0.95
DEFAULT_SEED = 0


@dataclass(frozen=True)
class BootstrapCI:
    mean: float
    low: float
    high: float
    confidence: float
    iterations: int
    seed: int


def quantile(sorted_values: Sequence[float], q: float) -> float:
    """Quantile of already-sorted values, linear interpolation (Hyndman-Fan type 7)."""
    if not sorted_values:
        raise ValueError("quantile of an empty sequence")
    if not 0.0 <= q <= 1.0:
        raise ValueError(f"quantile level must be in [0, 1], got {q}")
    h = (len(sorted_values) - 1) * q
    lo = math.floor(h)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (h - lo) * (sorted_values[hi] - sorted_values[lo])


def bootstrap_means(values: Sequence[float], *, iterations: int, seed: int) -> list[float]:
    """Return *iterations* bootstrap means of *values*, sorted, from ``random.Random(seed)``."""
    if not values:
        raise ValueError("bootstrap of an empty sequence")
    if iterations < 1:
        raise ValueError("iterations must be >= 1")
    # Seeded, reproducible resampling for statistics, not security.
    rng = random.Random(seed)  # nosec B311
    n = len(values)
    data = list(values)
    means = [math.fsum(rng.choices(data, k=n)) / n for _ in range(iterations)]
    means.sort()
    return means


def paired_bootstrap_ci(
    deltas: Sequence[float],
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    iterations: int = DEFAULT_ITERATIONS,
    seed: int = DEFAULT_SEED,
) -> BootstrapCI:
    """Percentile-bootstrap confidence interval for the mean of paired *deltas*.

    Deterministic for a given ``seed``. When every delta is equal the interval collapses to
    that value.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError(f"confidence must be in (0, 1), got {confidence}")
    means = bootstrap_means(deltas, iterations=iterations, seed=seed)
    alpha = 1.0 - confidence
    return BootstrapCI(
        mean=math.fsum(deltas) / len(deltas),
        low=quantile(means, alpha / 2.0),
        high=quantile(means, 1.0 - alpha / 2.0),
        confidence=confidence,
        iterations=iterations,
        seed=seed,
    )
