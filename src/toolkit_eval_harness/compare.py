"""Compare a candidate report with a baseline report and decide whether to gate.

Method (``CompareBudget.method == "bootstrap"``, the default):

1. **Same suite.** When both reports carry ``suite.sha256`` they must be equal; otherwise the
   result is ``reason: "suite_mismatch"`` (the CLI exits 4). Reports without a digest
   (pre-1.0, or imported without one) are compared with ``suite_check: "unverified"``.
2. **Pairing.** Cases are paired by id. A baseline case missing from the candidate counts as
   a candidate failure with score 0.0 (fail closed: dropping a case cannot hide a
   regression). Candidate-only cases are listed and ignored. With
   ``allow_suite_mismatch=True`` only the common ids are paired.
3. **Flips.** ``new_failures`` are cases that passed in the baseline and fail in the
   candidate; ``fixes`` are the reverse.
4. **Confidence interval.** A seeded paired percentile bootstrap (see :mod:`.stats`) gives a
   ``confidence`` interval for the mean per-case delta ``candidate - baseline``.
5. **Gate.** The regression upper bound is ``-ci_low / baseline_mean * 100`` percent (the
   baseline mean over the paired cases is treated as fixed). The comparison fails when that
   upper bound exceeds ``max_score_regression_pct``, so a gate passes only when the data
   support "the regression is within budget", not merely "the mean moved little". It also
   fails when ``max_new_failures`` is set and more cases flipped from pass to fail.

With ``method="mean"``, or when either report has no per-case scores, only the aggregate
``summary.score`` values are compared (the pre-1.0 behaviour).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .report import EvalReport
from .stats import DEFAULT_CONFIDENCE, DEFAULT_ITERATIONS, DEFAULT_SEED, paired_bootstrap_ci

METHODS = ("bootstrap", "mean")


@dataclass(frozen=True)
class CompareBudget:
    """Gate settings. Every field after the first was added in 1.0 with a default."""

    max_score_regression_pct: float = 2.0
    method: str = "bootstrap"
    confidence: float = DEFAULT_CONFIDENCE
    iterations: int = DEFAULT_ITERATIONS
    seed: int = DEFAULT_SEED
    max_new_failures: int | None = None
    allow_suite_mismatch: bool = False


def _case_score(case: dict[str, Any]) -> float | None:
    value = case.get("score")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    score = float(value)
    return score if math.isfinite(score) else None


def _case_passed(case: dict[str, Any], score: float) -> bool:
    flag = case.get("passed")
    return flag if isinstance(flag, bool) else score >= 1.0


def _scored_cases(report: EvalReport) -> dict[str, tuple[float, bool, list[str]]]:
    out: dict[str, tuple[float, bool, list[str]]] = {}
    for case in report.cases:
        if not isinstance(case, dict) or case.get("id") is None:
            continue
        score = _case_score(case)
        if score is None:
            continue
        tags = [str(t) for t in case.get("tags") or []]
        out[str(case["id"])] = (score, _case_passed(case, score), tags)
    return out


def _mean_only(baseline: EvalReport, candidate: EvalReport, budget: CompareBudget) -> dict:
    base = float(baseline.summary.get("score", 0.0))
    cand = float(candidate.summary.get("score", 0.0))

    if base <= 0:
        passed = cand > 0
        return {
            "passed": passed,
            "reason": "no_baseline_score" if passed else "no_baseline_score_and_candidate_zero",
            "method": "mean",
            "baseline_score": base,
            "candidate_score": cand,
            "score_regression_pct": None,
        }

    regression_pct = ((base - cand) / base) * 100.0
    passed = regression_pct <= budget.max_score_regression_pct
    return {
        "passed": passed,
        "reason": "ok" if passed else "score_regression",
        "method": "mean",
        "baseline_score": base,
        "candidate_score": cand,
        "score_regression_pct": regression_pct,
        "max_score_regression_pct": budget.max_score_regression_pct,
    }


def _suite_check(baseline: EvalReport, candidate: EvalReport) -> tuple[str, str, str]:
    base_sha = str(baseline.suite.get("sha256") or "")
    cand_sha = str(candidate.suite.get("sha256") or "")
    if base_sha and cand_sha:
        return ("match" if base_sha == cand_sha else "mismatch"), base_sha, cand_sha
    return "unverified", base_sha, cand_sha


def compare_reports(*, baseline: EvalReport, candidate: EvalReport, budget: CompareBudget) -> dict:
    """Compare *candidate* with *baseline*; see the module docstring for the method.

    The returned dict always has ``passed``, ``reason``, ``baseline_score``,
    ``candidate_score`` and ``score_regression_pct`` (as before 1.0). Reasons: ``ok``,
    ``score_regression``, ``new_failures``, ``suite_mismatch``, ``no_baseline_score``,
    ``no_baseline_score_and_candidate_zero``.
    """
    if budget.method not in METHODS:
        raise ValueError(f"unknown compare method {budget.method!r}; expected one of {METHODS}")

    suite_check, base_sha, cand_sha = _suite_check(baseline, candidate)
    if suite_check == "mismatch" and not budget.allow_suite_mismatch:
        return {
            "passed": False,
            "reason": "suite_mismatch",
            "method": budget.method,
            "suite_check": suite_check,
            "baseline_suite_sha256": base_sha,
            "candidate_suite_sha256": cand_sha,
            "baseline_score": float(baseline.summary.get("score", 0.0)),
            "candidate_score": float(candidate.summary.get("score", 0.0)),
            "score_regression_pct": None,
        }

    base_cases = _scored_cases(baseline)
    cand_cases = _scored_cases(candidate)
    if budget.method == "mean" or not base_cases or not cand_cases:
        result = _mean_only(baseline, candidate, budget)
        result.update(
            {
                "suite_check": suite_check,
                "baseline_suite_sha256": base_sha,
                "candidate_suite_sha256": cand_sha,
            }
        )
        return result

    only_in_baseline = sorted(set(base_cases) - set(cand_cases))
    only_in_candidate = sorted(set(cand_cases) - set(base_cases))
    if budget.allow_suite_mismatch:
        ids = [i for i in base_cases if i in cand_cases]
    else:
        ids = list(base_cases)  # missing candidate cases count as failures (score 0)

    base_scores: list[float] = []
    cand_scores: list[float] = []
    new_failures: list[str] = []
    fixes: list[str] = []
    per_tag: dict[str, dict[str, Any]] = {}
    for case_id in ids:
        b_score, b_pass, tags = base_cases[case_id]
        c_score, c_pass, c_tags = cand_cases.get(case_id, (0.0, False, tags))
        base_scores.append(b_score)
        cand_scores.append(c_score)
        if b_pass and not c_pass:
            new_failures.append(case_id)
        elif c_pass and not b_pass:
            fixes.append(case_id)
        for tag in dict.fromkeys(tags or c_tags):
            bucket = per_tag.setdefault(
                tag,
                {"cases": 0, "baseline_sum": 0.0, "candidate_sum": 0.0,
                 "new_failures": 0, "fixes": 0},
            )
            bucket["cases"] += 1
            bucket["baseline_sum"] += b_score
            bucket["candidate_sum"] += c_score
            bucket["new_failures"] += int(b_pass and not c_pass)
            bucket["fixes"] += int(c_pass and not b_pass)

    n = len(ids)
    base_mean = math.fsum(base_scores) / n
    cand_mean = math.fsum(cand_scores) / n
    deltas = [c - b for b, c in zip(base_scores, cand_scores, strict=True)]
    ci = paired_bootstrap_ci(
        deltas, confidence=budget.confidence, iterations=budget.iterations, seed=budget.seed
    )

    tags_out: dict[str, dict[str, Any]] = {}
    for tag in sorted(per_tag):
        bucket = per_tag[tag]
        k = bucket["cases"]
        b_mean = bucket["baseline_sum"] / k
        c_mean = bucket["candidate_sum"] / k
        tags_out[tag] = {
            "cases": k,
            "baseline_score": b_mean,
            "candidate_score": c_mean,
            "delta": c_mean - b_mean,
            "new_failures": bucket["new_failures"],
            "fixes": bucket["fixes"],
        }

    result: dict[str, Any] = {
        "method": "bootstrap",
        "suite_check": suite_check,
        "baseline_suite_sha256": base_sha,
        "candidate_suite_sha256": cand_sha,
        "paired_cases": n,
        "only_in_baseline": only_in_baseline,
        "only_in_candidate": only_in_candidate,
        "baseline_score": base_mean,
        "candidate_score": cand_mean,
        "mean_delta": ci.mean,
        "ci_low": ci.low,
        "ci_high": ci.high,
        "confidence": ci.confidence,
        "iterations": ci.iterations,
        "seed": ci.seed,
        "new_failures": new_failures,
        "fixes": fixes,
        "new_failure_count": len(new_failures),
        "fix_count": len(fixes),
        "max_new_failures": budget.max_new_failures,
        "max_score_regression_pct": budget.max_score_regression_pct,
        "per_tag": tags_out,
    }

    if base_mean <= 0:
        passed = cand_mean > 0
        result.update(
            {
                "passed": passed,
                "reason": "no_baseline_score" if passed
                else "no_baseline_score_and_candidate_zero",
                "score_regression_pct": None,
                "regression_pct_upper": None,
            }
        )
        return result

    regression_pct = -ci.mean / base_mean * 100.0
    regression_upper = -ci.low / base_mean * 100.0
    reason = "ok"
    if regression_upper > budget.max_score_regression_pct:
        reason = "score_regression"
    elif budget.max_new_failures is not None and len(new_failures) > budget.max_new_failures:
        reason = "new_failures"
    result.update(
        {
            "passed": reason == "ok",
            "reason": reason,
            "score_regression_pct": regression_pct,
            "regression_pct_upper": regression_upper,
        }
    )
    return result
