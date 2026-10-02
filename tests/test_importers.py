"""Importers: promptfoo, Inspect AI and DeepEval results -> normalized EvalReport.

Every fixture in tests/fixtures/importers/ was produced by the real tool (see the README
there for the exact commands and versions), so these tests pin the importers to the
formats the tools actually write, not to a hand-written guess.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from toolkit_eval_harness.cli import main
from toolkit_eval_harness.compare import CompareBudget, compare_reports
from toolkit_eval_harness.envelope import validate_envelope
from toolkit_eval_harness.importers import (
    import_deepeval,
    import_inspect,
    import_promptfoo,
    inspect_value_to_float,
)
from toolkit_eval_harness.report import EvalReport

FIX = Path(__file__).resolve().parent / "fixtures" / "importers"


def _cases(report: EvalReport) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in report.cases}


def _rewrite(tmp_path: Path, src: Path, mutate: Any, name: str | None = None) -> Path:
    data = json.loads(src.read_text(encoding="utf-8"))
    mutate(data)
    out = tmp_path / (name or src.name)
    out.write_text(json.dumps(data), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# promptfoo
# ---------------------------------------------------------------------------


def test_promptfoo_baseline_values() -> None:
    report = import_promptfoo(FIX / "promptfoo" / "baseline.json")
    cases = _cases(report)
    assert list(cases) == ["capital of France", "capital of Japan", "two plus two",
                           "weighted partial"]
    assert (cases["capital of France"]["score"], cases["capital of France"]["passed"]) == (1, True)
    assert (cases["capital of Japan"]["score"], cases["capital of Japan"]["passed"]) == (0, False)
    # Two weighted assertions, one passing: promptfoo scores 0.5 and fails the test.
    assert cases["weighted partial"]["score"] == 0.5
    assert cases["weighted partial"]["passed"] is False
    assert cases["capital of Japan"]["tags"] == ["provider:echo", "topic:geo"]
    assert report.summary["passed"] == 2 and report.summary["failed"] == 2
    assert report.suite["source"]["version"] == "0.123.1"


def test_promptfoo_same_tests_share_suite_digest_and_compare_finds_flips() -> None:
    base = import_promptfoo(FIX / "promptfoo" / "baseline.json")
    cand = import_promptfoo(FIX / "promptfoo" / "candidate.json")
    assert base.suite["sha256"] == cand.suite["sha256"]
    res = compare_reports(baseline=base, candidate=cand, budget=CompareBudget())
    assert res["suite_check"] == "match"
    assert res["new_failures"] == ["two plus two"]
    assert res["fixes"] == ["capital of Japan", "weighted partial"]


def test_promptfoo_changed_assertion_changes_digest(tmp_path: Path) -> None:
    def mutate(d: dict[str, Any]) -> None:
        d["results"]["results"][0]["testCase"]["assert"][0]["value"] = "Lyon"

    changed = import_promptfoo(_rewrite(tmp_path, FIX / "promptfoo" / "baseline.json", mutate))
    base = import_promptfoo(FIX / "promptfoo" / "baseline.json")
    assert changed.suite["sha256"] != base.suite["sha256"]


def test_promptfoo_error_row_fails_with_zero(tmp_path: Path) -> None:
    def mutate(d: dict[str, Any]) -> None:
        row = d["results"]["results"][0]
        row.update({"success": False, "failureReason": 2, "error": "provider timeout",
                    "score": 0})
        row.pop("gradingResult", None)

    report = import_promptfoo(_rewrite(tmp_path, FIX / "promptfoo" / "baseline.json", mutate))
    case = _cases(report)["capital of France"]
    assert case["passed"] is False and case["score"] == 0.0
    assert case["error"] == "provider timeout"


def test_promptfoo_duplicate_descriptions_fall_back_to_indices(tmp_path: Path) -> None:
    def mutate(d: dict[str, Any]) -> None:
        for row in d["results"]["results"]:
            row["testCase"]["description"] = "same"

    report = import_promptfoo(_rewrite(tmp_path, FIX / "promptfoo" / "baseline.json", mutate))
    assert [c["id"] for c in report.cases] == ["test-0", "test-1", "test-2", "test-3"]


def test_promptfoo_multiple_providers_and_filter(tmp_path: Path) -> None:
    def mutate(d: dict[str, Any]) -> None:
        rows = d["results"]["results"]
        extra = copy.deepcopy(rows)
        for row in extra:
            row["provider"] = {"id": "openai:gpt-x", "label": ""}
        rows.extend(extra)

    path = _rewrite(tmp_path, FIX / "promptfoo" / "baseline.json", mutate)
    both = import_promptfoo(path)
    assert "capital of France@echo" in _cases(both)
    assert "capital of France@openai:gpt-x" in _cases(both)
    only = import_promptfoo(path, provider="openai:gpt-x")
    assert list(_cases(only))[0] == "capital of France"
    with pytest.raises(ValueError, match="unknown_provider"):
        import_promptfoo(path, provider="nope")


# ---------------------------------------------------------------------------
# Inspect AI
# ---------------------------------------------------------------------------


def test_inspect_value_to_float_matches_inspect() -> None:
    """Reference: inspect_ai 0.3.270 ``value_to_float()`` evaluated in a container.

    Output there: C->1.0, I->0.0, P->0.5, N->0.0, 'yes'->1.0, 'No'->0.0, 'TRUE'->1.0,
    'false'->0.0, '0.75'->0.75, '3'->3.0, 1->1.0, 0->0.0, 0.5->0.5, True->1.0, False->0.0,
    'maybe'->0.0 (with a warning), '1.2.3'->0.0 (with a warning). The importer returns None
    where Inspect warns, so the case can be flagged.
    """
    reference: list[tuple[Any, float]] = [
        ("C", 1.0), ("I", 0.0), ("P", 0.5), ("N", 0.0), ("yes", 1.0), ("No", 0.0),
        ("TRUE", 1.0), ("false", 0.0), ("0.75", 0.75), ("3", 3.0), (1, 1.0), (0, 0.0),
        (0.5, 0.5), (True, 1.0), (False, 0.0),
    ]
    for value, expected in reference:
        assert inspect_value_to_float(value) == expected, value
    for warned in ("maybe", "1.2.3", [1], {"a": 1}):
        assert inspect_value_to_float(warned) is None


def test_inspect_json_log() -> None:
    report = import_inspect(FIX / "inspect" / "capitals.json")
    cases = _cases(report)
    assert list(cases) == ["fr", "jp", "math-1"]
    assert cases["fr"]["passed"] is True and cases["fr"]["scores"] == {"includes": 1.0,
                                                                      "match": 1.0}
    assert cases["jp"]["passed"] is False and cases["jp"]["score"] == 0.0
    assert cases["math-1"]["tags"] == ["topic:math"]
    assert report.summary["scorers"] == ["includes", "match"]
    assert report.suite["name"] == "capitals"
    assert report.suite["source"]["model"] == "mockllm/model"


def test_inspect_eval_archive_matches_json_log() -> None:
    pytest.importorskip("zstandard")
    from_eval = import_inspect(FIX / "inspect" / "capitals.eval")
    from_json = import_inspect(FIX / "inspect" / "capitals.json")
    assert from_eval.suite["sha256"] == from_json.suite["sha256"]
    assert [(c["id"], c["score"], c["passed"]) for c in from_eval.cases] == [
        (c["id"], c["score"], c["passed"]) for c in from_json.cases
    ]


def test_inspect_epochs_are_reduced_to_one_case_per_sample() -> None:
    pytest.importorskip("zstandard")
    report = import_inspect(FIX / "inspect" / "capitals-2-epochs.eval")
    assert [c["epochs"] for c in report.cases] == [2, 2, 2]
    assert report.summary["cases"] == 3


def test_inspect_missing_and_errored_samples_fail(tmp_path: Path) -> None:
    def mutate(d: dict[str, Any]) -> None:
        d["samples"] = [s for s in d["samples"] if s["id"] != "math-1"]
        d["samples"][0]["error"] = {"message": "sandbox crashed"}

    report = import_inspect(_rewrite(tmp_path, FIX / "inspect" / "capitals.json", mutate))
    cases = _cases(report)
    assert cases["math-1"]["missing_prediction"] is True and cases["math-1"]["passed"] is False
    assert cases["fr"]["passed"] is False and cases["fr"]["score"] == 0.0
    assert report.summary["missing_predictions"] == 1


def test_inspect_scorer_filter() -> None:
    report = import_inspect(FIX / "inspect" / "capitals.json", scorer="includes")
    assert report.summary["scorers"] == ["includes"]
    with pytest.raises(ValueError, match="unknown_scorer"):
        import_inspect(FIX / "inspect" / "capitals.json", scorer="f1")


# ---------------------------------------------------------------------------
# DeepEval
# ---------------------------------------------------------------------------


def test_deepeval_test_run() -> None:
    report = import_deepeval(FIX / "deepeval" / "test_run.json")
    cases = _cases(report)
    assert list(cases) == ["france", "japan", "essay"]
    assert cases["france"]["passed"] is True
    assert cases["japan"]["passed"] is False and cases["japan"]["score"] == 0.0
    # 'essay' passes Contains Expected but fails Length Under (0.25 < threshold 0.5).
    assert cases["essay"]["passed"] is False and cases["essay"]["score"] == 0.25
    assert cases["essay"]["failed_metrics"] == ["Length Under"]
    assert report.summary["passed"] == 1
    assert report.summary["scorers"] == ["Contains Expected", "Length Under"]


def test_deepeval_metric_filter_and_errors(tmp_path: Path) -> None:
    only_length = import_deepeval(FIX / "deepeval" / "test_run.json", metric="Length Under")
    assert _cases(only_length)["japan"]["passed"] is True

    def mutate(d: dict[str, Any]) -> None:
        m = d["testCases"][0]["metricsData"][0]
        m.update({"error": "judge unavailable", "score": None, "success": False})

    errored = import_deepeval(_rewrite(tmp_path, FIX / "deepeval" / "test_run.json", mutate))
    assert _cases(errored)["france"]["passed"] is False
    with pytest.raises(ValueError, match="unknown_metric"):
        import_deepeval(FIX / "deepeval" / "test_run.json", metric="Faithfulness")


def test_deepeval_duplicate_names_rejected(tmp_path: Path) -> None:
    def mutate(d: dict[str, Any]) -> None:
        for c in d["testCases"]:
            c["name"] = "same"

    with pytest.raises(ValueError, match="duplicate_case_id"):
        import_deepeval(_rewrite(tmp_path, FIX / "deepeval" / "test_run.json", mutate))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_import_writes_envelope_and_gates(tmp_path: Path) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(
        (Path(__file__).resolve().parents[1] / "schemas" / "report-envelope.v1.json").read_text(
            encoding="utf-8"
        )
    )
    base, cand = tmp_path / "base.json", tmp_path / "cand.json"
    assert main(["import", "promptfoo", str(FIX / "promptfoo" / "baseline.json"),
                 "--out", str(base)]) == 1  # two failing cases
    assert main(["import", "promptfoo", str(FIX / "promptfoo" / "candidate.json"),
                 "--out", str(cand)]) == 1
    env = json.loads(base.read_text(encoding="utf-8"))
    jsonschema.validate(env, schema)
    assert validate_envelope(env) == []
    pred = env["predicate"]
    assert pred["kind"] == "eval.import" and pred["verdict"] == "fail"
    assert pred["details"]["source"] == "promptfoo"
    assert env["subject"][0]["digest"]["sha256"] == pred["details"]["suite"]["sha256"]
    assert main(["validate-report", "--report", str(base)]) == 0

    out = tmp_path / "cmp.json"
    rc = main(["compare", "--baseline", str(base), "--candidate", str(cand), "--out", str(out),
               "--max-score-regression-pct", "100"])
    assert rc == 0
    summary = json.loads(out.read_text(encoding="utf-8"))["predicate"]["summary"]
    assert summary["suite_check"] == "match"
    assert summary["new_failure_count"] == 1 and summary["fix_count"] == 2


def test_cli_import_bad_file_is_input_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    for source in ("promptfoo", "inspect", "deepeval"):
        assert main(["import", source, str(bad)]) == 2
    assert main(["import", "deepeval", str(tmp_path / "missing.json")]) == 2
