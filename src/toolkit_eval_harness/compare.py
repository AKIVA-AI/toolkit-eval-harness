from __future__ import annotations

from dataclasses import dataclass

from .report import EvalReport


@dataclass(frozen=True)
class CompareBudget:
    max_score_regression_pct: float = 2.0


def compare_reports(*, baseline: EvalReport, candidate: EvalReport, budget: CompareBudget) -> dict:
    base = float(baseline.summary.get("score", 0.0))
    cand = float(candidate.summary.get("score", 0.0))

    if base <= 0:
        passed = cand > 0
        return {
            "passed": passed,
            "reason": "no_baseline_score" if passed else "no_baseline_score_and_candidate_zero",
            "baseline_score": base,
            "candidate_score": cand,
            "score_regression_pct": None,
        }

    regression_pct = ((base - cand) / base) * 100.0
    passed = regression_pct <= budget.max_score_regression_pct
    return {
        "passed": passed,
        "reason": "ok" if passed else "score_regression",
        "baseline_score": base,
        "candidate_score": cand,
        "score_regression_pct": regression_pct,
        "max_score_regression_pct": budget.max_score_regression_pct,
    }
