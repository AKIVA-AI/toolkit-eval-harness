"""Statistically sound compare: paired bootstrap CI, flips, per-tag breakdown, suite binding.

Reference values
----------------
The bootstrap is checked against ``scipy.stats.bootstrap`` (SciPy 1.16.2, NumPy 2.3.3),
computed in a python:3.12-slim container with::

    bootstrap((b, c), lambda x, y, axis=-1: np.mean(y - x, axis=axis), paired=True,
              vectorized=True, n_resamples=200000, confidence_level=conf,
              method="percentile", random_state=np.random.default_rng(12345))

on the two datasets built by ``_continuous()`` and ``_binary()`` below. Results:

    continuous, 0.95: low=-0.108833 high=0.105667
    continuous, 0.90: low=-0.091667 high=0.088500
    binary,     0.95: low=-0.175000 high=0.025000
    binary,     0.90: low=-0.175000 high=0.000000

Different RNGs give different resamples, so agreement is up to Monte Carlo error: 0.01 for
the continuous data, and one lattice step (1/n = 0.025) for the binary data, whose bootstrap
means can only take multiples of 1/n.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest

from toolkit_eval_harness.cli import main
from toolkit_eval_harness.compare import CompareBudget, compare_reports
from toolkit_eval_harness.report import EvalReport
from toolkit_eval_harness.stats import bootstrap_means, paired_bootstrap_ci, quantile


def _continuous() -> tuple[list[float], list[float]]:
    base = [((i * 37) % 101) / 100 for i in range(60)]
    cand = [((i * 53 + 11) % 101) / 100 for i in range(60)]
    return base, cand


def _binary() -> tuple[list[float], list[float]]:
    # 40 cases: 30 pass in both, 4 pass->fail, 1 fail->pass, 5 fail in both.
    base = [1.0] * 30 + [1.0] * 4 + [0.0] * 1 + [0.0] * 5
    cand = [1.0] * 30 + [0.0] * 4 + [1.0] * 1 + [0.0] * 5
    return base, cand


# ---------------------------------------------------------------------------
# stats primitives
# ---------------------------------------------------------------------------


def test_quantile_matches_numpy_linear_method() -> None:
    # NumPy docs, numpy.percentile example: np.percentile([[10, 7, 4], [3, 2, 1]], 50) == 3.5
    assert quantile(sorted([10, 7, 4, 3, 2, 1]), 0.5) == pytest.approx(3.5)
    # Type-7 by hand: h = (4 - 1) * 0.25 = 0.75 -> 1 + 0.75 * (2 - 1)
    assert quantile([1.0, 2.0, 3.0, 4.0], 0.25) == pytest.approx(1.75)
    assert quantile([1.0, 2.0, 3.0, 4.0], 0.0) == 1.0
    assert quantile([1.0, 2.0, 3.0, 4.0], 1.0) == 4.0


@pytest.mark.parametrize(
    "dataset,confidence,ref_low,ref_high,tol",
    [
        (_continuous, 0.95, -0.108833, 0.105667, 0.01),
        (_continuous, 0.90, -0.091667, 0.088500, 0.01),
        (_binary, 0.95, -0.175, 0.025, 0.025),
        (_binary, 0.90, -0.175, 0.0, 0.025),
    ],
)
def test_paired_bootstrap_matches_scipy(
    dataset: Any, confidence: float, ref_low: float, ref_high: float, tol: float
) -> None:
    base, cand = dataset()
    deltas = [c - b for b, c in zip(base, cand, strict=True)]
    ci = paired_bootstrap_ci(deltas, confidence=confidence, iterations=20_000, seed=7)
    assert ci.mean == pytest.approx(sum(deltas) / len(deltas))
    assert ci.low == pytest.approx(ref_low, abs=tol)
    assert ci.high == pytest.approx(ref_high, abs=tol)


def test_bootstrap_resampling_matches_exact_distribution() -> None:
    """Worked example with an exact answer.

    For deltas [0, 0, -1] a resample of size 3 contains k copies of -1 with
    k ~ Binomial(3, 1/3), so the bootstrap mean is -k/3 with probabilities
    8/27, 12/27, 6/27, 1/27 for k = 0..3.
    """
    iterations = 30_000
    means = bootstrap_means([0.0, 0.0, -1.0], iterations=iterations, seed=3)
    exact = {0: 8 / 27, 1: 12 / 27, 2: 6 / 27, 3: 1 / 27}
    for k, p in exact.items():
        observed = sum(1 for m in means if math.isclose(m, -k / 3, abs_tol=1e-12)) / iterations
        sigma = math.sqrt(p * (1 - p) / iterations)
        assert abs(observed - p) < 4 * sigma, (k, observed, p)


def test_bootstrap_is_deterministic_for_a_seed() -> None:
    base, cand = _continuous()
    deltas = [c - b for b, c in zip(base, cand, strict=True)]
    a = paired_bootstrap_ci(deltas, iterations=2000, seed=1)
    b = paired_bootstrap_ci(deltas, iterations=2000, seed=1)
    c = paired_bootstrap_ci(deltas, iterations=2000, seed=2)
    assert (a.low, a.high) == (b.low, b.high)
    assert (a.low, a.high) != (c.low, c.high)


def test_bootstrap_collapses_when_all_deltas_equal() -> None:
    ci = paired_bootstrap_ci([0.25] * 10, iterations=500)
    assert ci.low == pytest.approx(0.25) and ci.high == pytest.approx(0.25)


@pytest.mark.parametrize("bad", [0.0, 1.0, 1.5])
def test_bootstrap_rejects_bad_confidence(bad: float) -> None:
    with pytest.raises(ValueError):
        paired_bootstrap_ci([0.0, 1.0], confidence=bad)


# ---------------------------------------------------------------------------
# compare_reports
# ---------------------------------------------------------------------------


def _report(
    scores: dict[str, float], *, sha: str = "a" * 64, tags: dict[str, list[str]] | None = None
) -> EvalReport:
    tags = tags or {}
    cases = [
        {"id": cid, "score": s, "passed": s >= 1.0, "tags": tags.get(cid, [])}
        for cid, s in scores.items()
    ]
    mean = sum(scores.values()) / len(scores) if scores else 0.0
    return EvalReport(suite={"name": "s", "sha256": sha}, summary={"score": mean}, cases=cases)


def _binary_reports() -> tuple[EvalReport, EvalReport]:
    base, cand = _binary()
    ids = [f"c{i:02d}" for i in range(len(base))]
    return _report(dict(zip(ids, base, strict=True))), _report(dict(zip(ids, cand, strict=True)))


def test_net_zero_churn_fails_bootstrap_gate_but_passes_mean_gate() -> None:
    """The case the brief calls out: 2 cases break, 2 get fixed, mean unchanged."""
    ids = [f"c{i:02d}" for i in range(20)]
    base = {i: 1.0 for i in ids}
    cand = dict(base)
    base.update({"c00": 0.0, "c01": 0.0})
    cand.update({"c02": 0.0, "c03": 0.0})
    b, c = _report(base), _report(cand)

    mean_only = compare_reports(baseline=b, candidate=c, budget=CompareBudget(method="mean"))
    assert mean_only["passed"] is True

    res = compare_reports(baseline=b, candidate=c, budget=CompareBudget())
    assert res["method"] == "bootstrap"
    assert res["mean_delta"] == pytest.approx(0.0)
    assert res["score_regression_pct"] == pytest.approx(0.0)
    assert res["regression_pct_upper"] > 2.0
    assert res["passed"] is False and res["reason"] == "score_regression"
    assert res["new_failures"] == ["c02", "c03"]
    assert res["fixes"] == ["c00", "c01"]


def test_identical_reports_pass_with_zero_width_interval() -> None:
    b, _ = _binary_reports()
    res = compare_reports(baseline=b, candidate=b, budget=CompareBudget(max_score_regression_pct=0))
    assert res["passed"] is True
    assert res["ci_low"] == 0.0 and res["ci_high"] == 0.0
    assert res["new_failure_count"] == 0 and res["fix_count"] == 0


def test_clear_regression_fails_and_improvement_passes() -> None:
    b, c = _binary_reports()
    worse = compare_reports(baseline=b, candidate=c, budget=CompareBudget())
    assert worse["passed"] is False
    assert worse["new_failure_count"] == 4 and worse["fix_count"] == 1
    assert worse["baseline_score"] == pytest.approx(34 / 40)
    assert worse["candidate_score"] == pytest.approx(31 / 40)
    # Reversed, the mean improves, but 4 of the 5 flips are fixes and 1 is a break, so the
    # interval still reaches a regression above 2 %: not a clear improvement.
    mixed = compare_reports(baseline=c, candidate=b, budget=CompareBudget())
    assert mixed["score_regression_pct"] < 0
    assert mixed["passed"] is False
    # Fixes only: every delta is >= 0, so the upper bound of the regression is <= 0.
    all_pass = _report({case["id"]: 1.0 for case in c.cases})
    better = compare_reports(baseline=c, candidate=all_pass, budget=CompareBudget())
    assert better["passed"] is True
    assert better["regression_pct_upper"] <= 0


def test_gate_uses_the_upper_bound_not_the_mean() -> None:
    b, c = _binary_reports()
    res = compare_reports(baseline=b, candidate=c, budget=CompareBudget())
    expected_upper = -res["ci_low"] / res["baseline_score"] * 100
    assert res["regression_pct_upper"] == pytest.approx(expected_upper)
    assert res["regression_pct_upper"] > res["score_regression_pct"]
    # A budget between the point estimate and the upper bound fails.
    budget = (res["score_regression_pct"] + res["regression_pct_upper"]) / 2
    mid = compare_reports(
        baseline=b, candidate=c, budget=CompareBudget(max_score_regression_pct=budget)
    )
    assert mid["passed"] is False
    loose = compare_reports(
        baseline=b,
        candidate=c,
        budget=CompareBudget(max_score_regression_pct=res["regression_pct_upper"] + 0.01),
    )
    assert loose["passed"] is True


def test_max_new_failures_gate() -> None:
    b, c = _binary_reports()
    budget = CompareBudget(max_score_regression_pct=100.0, max_new_failures=3)
    res = compare_reports(baseline=b, candidate=c, budget=budget)
    assert res["passed"] is False and res["reason"] == "new_failures"
    ok = compare_reports(
        baseline=b, candidate=c,
        budget=CompareBudget(max_score_regression_pct=100.0, max_new_failures=4),
    )
    assert ok["passed"] is True


def test_per_tag_breakdown() -> None:
    tags = {"a": ["geo"], "b": ["geo", "math"], "c": ["math"]}
    b = _report({"a": 1.0, "b": 1.0, "c": 0.0}, tags=tags)
    c = _report({"a": 1.0, "b": 0.0, "c": 1.0}, tags=tags)
    budget = CompareBudget(max_score_regression_pct=100)
    res = compare_reports(baseline=b, candidate=c, budget=budget)
    assert res["per_tag"]["geo"] == {
        "cases": 2, "baseline_score": 1.0, "candidate_score": 0.5, "delta": -0.5,
        "new_failures": 1, "fixes": 0,
    }
    assert res["per_tag"]["math"] == {
        "cases": 2, "baseline_score": 0.5, "candidate_score": 0.5, "delta": 0.0,
        "new_failures": 1, "fixes": 1,
    }


def test_suite_mismatch_is_refused_unless_allowed() -> None:
    b = _report({"x": 1.0, "y": 1.0}, sha="a" * 64)
    c = _report({"x": 1.0, "z": 0.0}, sha="b" * 64)
    res = compare_reports(baseline=b, candidate=c, budget=CompareBudget())
    assert res["passed"] is False and res["reason"] == "suite_mismatch"
    allowed = compare_reports(
        baseline=b, candidate=c, budget=CompareBudget(allow_suite_mismatch=True)
    )
    assert allowed["suite_check"] == "mismatch"
    assert allowed["paired_cases"] == 1
    assert allowed["only_in_baseline"] == ["y"] and allowed["only_in_candidate"] == ["z"]
    assert allowed["passed"] is True


def test_missing_candidate_case_counts_as_failure() -> None:
    b = EvalReport(suite={}, summary={"score": 1.0}, cases=[
        {"id": "x", "score": 1.0, "passed": True}, {"id": "y", "score": 1.0, "passed": True},
    ])
    c = EvalReport(suite={}, summary={"score": 1.0}, cases=[
        {"id": "x", "score": 1.0, "passed": True},
    ])
    res = compare_reports(baseline=b, candidate=c, budget=CompareBudget())
    assert res["suite_check"] == "unverified"
    assert res["only_in_baseline"] == ["y"]
    assert res["new_failures"] == ["y"]
    assert res["candidate_score"] == pytest.approx(0.5)
    assert res["passed"] is False


def test_summary_only_reports_fall_back_to_mean() -> None:
    b = EvalReport(suite={}, summary={"score": 1.0}, cases=[])
    c = EvalReport(suite={}, summary={"score": 0.99}, cases=[])
    res = compare_reports(baseline=b, candidate=c, budget=CompareBudget())
    assert res["method"] == "mean" and res["passed"] is True


def test_unknown_method_rejected() -> None:
    b, c = _binary_reports()
    with pytest.raises(ValueError):
        compare_reports(baseline=b, candidate=c, budget=CompareBudget(method="t-test"))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _write(path: Path, report: EvalReport) -> Path:
    path.write_text(json.dumps(report.to_dict()), encoding="utf-8")
    return path


def test_cli_suite_mismatch_exits_4_with_error_envelope(tmp_path: Path) -> None:
    b = _write(tmp_path / "b.json", _report({"x": 1.0}, sha="a" * 64))
    c = _write(tmp_path / "c.json", _report({"x": 1.0}, sha="b" * 64))
    out = tmp_path / "cmp.json"
    rc = main(["compare", "--baseline", str(b), "--candidate", str(c), "--out", str(out)])
    assert rc == 4
    env = json.loads(out.read_text(encoding="utf-8"))
    assert env["predicate"]["verdict"] == "error"
    assert env["predicate"]["summary"]["reason"] == "suite_mismatch"
    rc = main(["compare", "--baseline", str(b), "--candidate", str(c),
               "--allow-suite-mismatch"])
    assert rc == 0


def test_cli_compare_envelope_carries_interval_and_flips(tmp_path: Path) -> None:
    base, cand = _binary_reports()
    b = _write(tmp_path / "b.json", base)
    c = _write(tmp_path / "c.json", cand)
    out = tmp_path / "cmp.json"
    rc = main(["compare", "--baseline", str(b), "--candidate", str(c), "--out", str(out),
               "--iterations", "2000", "--seed", "5", "--confidence", "0.9"])
    assert rc == 1
    pred = json.loads(out.read_text(encoding="utf-8"))["predicate"]
    assert pred["verdict"] == "fail"
    s = pred["summary"]
    assert s["confidence"] == 0.9 and s["method"] == "bootstrap"
    assert s["ci_low"] <= s["mean_delta"] <= s["ci_high"]
    assert s["new_failure_count"] == 4 and s["fix_count"] == 1
    assert pred["details"]["iterations"] == 2000 and pred["details"]["seed"] == 5
    assert len(pred["details"]["new_failures"]) == 4


def test_cli_max_new_failures_flag(tmp_path: Path) -> None:
    base, cand = _binary_reports()
    b = _write(tmp_path / "b.json", base)
    c = _write(tmp_path / "c.json", cand)
    args = ["compare", "--baseline", str(b), "--candidate", str(c),
            "--max-score-regression-pct", "100"]
    assert main(args) == 0
    assert main([*args, "--max-new-failures", "0"]) == 1
