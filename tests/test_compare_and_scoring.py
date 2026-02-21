from __future__ import annotations

from toolkit_eval_harness.compare import CompareBudget, compare_reports
from toolkit_eval_harness.report import EvalReport
from toolkit_eval_harness.scoring import JSONSchema, exact_match_score, json_required_keys_score


def test_exact_match_score() -> None:
    assert exact_match_score(expected="x", predicted="x")[0] == 1.0
    assert exact_match_score(expected="x", predicted="y")[0] == 0.0


def test_json_required_keys_score_invalid_json() -> None:
    schema = JSONSchema(required_keys=["a"], optional_keys=[], allow_extra_keys=True)
    score, meta = json_required_keys_score(schema=schema, predicted="{not json")
    assert score == 0.0
    assert meta["json_valid"] is False


def test_json_required_keys_score_dict() -> None:
    schema = JSONSchema(required_keys=["a", "b"], optional_keys=[], allow_extra_keys=True)
    score, meta = json_required_keys_score(schema=schema, predicted={"a": 1, "b": 2, "c": 3})
    assert score == 1.0
    assert meta["json_valid"] is True


def test_compare_reports_regression_budget() -> None:
    baseline = EvalReport(suite={}, summary={"score": 1.0}, cases=[])
    candidate_ok = EvalReport(suite={}, summary={"score": 0.99}, cases=[])
    candidate_bad = EvalReport(suite={}, summary={"score": 0.90}, cases=[])

    budget = CompareBudget(max_score_regression_pct=2.0)
    ok = compare_reports(baseline=baseline, candidate=candidate_ok, budget=budget)
    bad = compare_reports(baseline=baseline, candidate=candidate_bad, budget=budget)
    assert ok["passed"] is True
    assert bad["passed"] is False


def test_compare_reports_no_baseline_score() -> None:
    baseline = EvalReport(suite={}, summary={"score": 0.0}, cases=[])
    candidate = EvalReport(suite={}, summary={"score": 0.5}, cases=[])
    out = compare_reports(baseline=baseline, candidate=candidate, budget=CompareBudget())
    assert out["passed"] is True

