"""Comprehensive tests: all scorer types, compare budget edge cases, pack/unpack round-trips."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from toolkit_eval_harness.compare import CompareBudget, compare_reports
from toolkit_eval_harness.pack import create_pack, load_suite_from_path, verify_pack
from toolkit_eval_harness.report import EvalReport
from toolkit_eval_harness.runner import run_suite
from toolkit_eval_harness.scoring import (
    JSONSchema,
    exact_match_score,
    json_required_keys_score,
    parse_json_schema,
    validate_json,
)
from toolkit_eval_harness.cli import EXIT_SUCCESS, EXIT_VALIDATION_FAILED, main


# ============================================================================
# Scorer: exact_match comprehensive
# ============================================================================


class TestExactMatchScorer:
    def test_string_match(self) -> None:
        score, meta = exact_match_score(expected="hello", predicted="hello")
        assert score == 1.0
        assert meta["match"] is True

    def test_string_mismatch(self) -> None:
        score, meta = exact_match_score(expected="hello", predicted="world")
        assert score == 0.0
        assert meta["match"] is False

    def test_int_match(self) -> None:
        score, _ = exact_match_score(expected=42, predicted=42)
        assert score == 1.0

    def test_int_mismatch(self) -> None:
        score, _ = exact_match_score(expected=42, predicted=43)
        assert score == 0.0

    def test_dict_match(self) -> None:
        score, _ = exact_match_score(expected={"a": 1}, predicted={"a": 1})
        assert score == 1.0

    def test_dict_mismatch(self) -> None:
        score, _ = exact_match_score(expected={"a": 1}, predicted={"a": 2})
        assert score == 0.0

    def test_list_match(self) -> None:
        score, _ = exact_match_score(expected=[1, 2, 3], predicted=[1, 2, 3])
        assert score == 1.0

    def test_none_match(self) -> None:
        score, _ = exact_match_score(expected=None, predicted=None)
        assert score == 1.0

    def test_none_mismatch(self) -> None:
        score, _ = exact_match_score(expected=None, predicted="something")
        assert score == 0.0

    def test_bool_match(self) -> None:
        score, _ = exact_match_score(expected=True, predicted=True)
        assert score == 1.0

    def test_empty_string(self) -> None:
        score, _ = exact_match_score(expected="", predicted="")
        assert score == 1.0

    def test_case_sensitive(self) -> None:
        score, _ = exact_match_score(expected="Hello", predicted="hello")
        assert score == 0.0


# ============================================================================
# Scorer: json_required_keys comprehensive
# ============================================================================


class TestJsonRequiredKeysScorer:
    def test_all_keys_present(self) -> None:
        schema = JSONSchema(required_keys=["a", "b"], optional_keys=[], allow_extra_keys=True)
        score, meta = json_required_keys_score(schema=schema, predicted={"a": 1, "b": 2})
        assert score == 1.0
        assert meta["json_valid"] is True

    def test_partial_keys(self) -> None:
        schema = JSONSchema(required_keys=["a", "b", "c"], optional_keys=[], allow_extra_keys=True)
        score, meta = json_required_keys_score(schema=schema, predicted={"a": 1})
        assert abs(score - 1 / 3) < 0.01

    def test_no_keys_present(self) -> None:
        schema = JSONSchema(required_keys=["a", "b"], optional_keys=[], allow_extra_keys=True)
        score, meta = json_required_keys_score(schema=schema, predicted={"x": 1})
        assert score == 0.0

    def test_json_string_input(self) -> None:
        schema = JSONSchema(required_keys=["status"], optional_keys=[], allow_extra_keys=True)
        score, meta = json_required_keys_score(
            schema=schema, predicted='{"status": "ok"}'
        )
        assert score == 1.0

    def test_invalid_json_string(self) -> None:
        schema = JSONSchema(required_keys=["a"], optional_keys=[], allow_extra_keys=True)
        score, meta = json_required_keys_score(schema=schema, predicted="{not json")
        assert score == 0.0
        assert meta["json_valid"] is False

    def test_non_dict_json(self) -> None:
        schema = JSONSchema(required_keys=["a"], optional_keys=[], allow_extra_keys=True)
        score, meta = json_required_keys_score(schema=schema, predicted=[1, 2, 3])
        assert score == 0.0

    def test_empty_required_keys(self) -> None:
        schema = JSONSchema(required_keys=[], optional_keys=[], allow_extra_keys=True)
        score, meta = json_required_keys_score(schema=schema, predicted={"any": "thing"})
        assert score == 1.0

    def test_extra_keys_disallowed(self) -> None:
        schema = JSONSchema(
            required_keys=["a"], optional_keys=["b"], allow_extra_keys=False
        )
        score, meta = json_required_keys_score(
            schema=schema, predicted={"a": 1, "b": 2, "extra": 3}
        )
        # Score is based on required keys present (1/1 = 1.0) but validation fails
        assert score == 1.0
        assert meta["json_valid"] is False

    def test_none_predicted(self) -> None:
        schema = JSONSchema(required_keys=["a"], optional_keys=[], allow_extra_keys=True)
        score, meta = json_required_keys_score(schema=schema, predicted=None)
        assert score == 0.0

    def test_number_predicted(self) -> None:
        schema = JSONSchema(required_keys=["a"], optional_keys=[], allow_extra_keys=True)
        score, meta = json_required_keys_score(schema=schema, predicted=42)
        assert score == 0.0


# ============================================================================
# validate_json
# ============================================================================


class TestValidateJson:
    def test_valid(self) -> None:
        schema = JSONSchema(required_keys=["x"], optional_keys=[], allow_extra_keys=True)
        ok, reasons = validate_json({"x": 1, "y": 2}, schema)
        assert ok is True
        assert reasons == []

    def test_missing_required(self) -> None:
        schema = JSONSchema(required_keys=["x", "y"], optional_keys=[], allow_extra_keys=True)
        ok, reasons = validate_json({"x": 1}, schema)
        assert ok is False
        assert any("missing_key:y" in r for r in reasons)

    def test_extra_keys_rejected(self) -> None:
        schema = JSONSchema(required_keys=["x"], optional_keys=[], allow_extra_keys=False)
        ok, reasons = validate_json({"x": 1, "extra": 2}, schema)
        assert ok is False
        assert any("extra_keys" in r for r in reasons)

    def test_not_object(self) -> None:
        schema = JSONSchema(required_keys=["x"], optional_keys=[], allow_extra_keys=True)
        ok, reasons = validate_json("not a dict", schema)
        assert ok is False
        assert "not_object" in reasons


class TestParseJsonSchema:
    def test_defaults(self) -> None:
        schema = parse_json_schema({})
        assert schema.required_keys == []
        assert schema.optional_keys == []
        assert schema.allow_extra_keys is True

    def test_full(self) -> None:
        schema = parse_json_schema({
            "required_keys": ["a", "b"],
            "optional_keys": ["c"],
            "allow_extra_keys": False,
        })
        assert schema.required_keys == ["a", "b"]
        assert schema.optional_keys == ["c"]
        assert schema.allow_extra_keys is False


# ============================================================================
# Compare budget edge cases
# ============================================================================


class TestCompareBudgetEdgeCases:
    def test_zero_regression_budget(self) -> None:
        """Budget of 0% means any regression fails."""
        baseline = EvalReport(suite={}, summary={"score": 1.0}, cases=[])
        candidate = EvalReport(suite={}, summary={"score": 0.999}, cases=[])
        budget = CompareBudget(max_score_regression_pct=0.0)
        result = compare_reports(baseline=baseline, candidate=candidate, budget=budget)
        assert result["passed"] is False

    def test_improvement_passes(self) -> None:
        """Candidate scoring higher than baseline always passes."""
        baseline = EvalReport(suite={}, summary={"score": 0.5}, cases=[])
        candidate = EvalReport(suite={}, summary={"score": 0.9}, cases=[])
        result = compare_reports(
            baseline=baseline, candidate=candidate, budget=CompareBudget()
        )
        assert result["passed"] is True
        assert result["score_regression_pct"] < 0  # negative = improvement

    def test_equal_scores_pass(self) -> None:
        baseline = EvalReport(suite={}, summary={"score": 0.8}, cases=[])
        candidate = EvalReport(suite={}, summary={"score": 0.8}, cases=[])
        result = compare_reports(
            baseline=baseline, candidate=candidate, budget=CompareBudget()
        )
        assert result["passed"] is True
        assert result["score_regression_pct"] == 0.0

    def test_both_zero_fails(self) -> None:
        """Both baseline and candidate at 0 fails (no_baseline_score_and_candidate_zero)."""
        baseline = EvalReport(suite={}, summary={"score": 0.0}, cases=[])
        candidate = EvalReport(suite={}, summary={"score": 0.0}, cases=[])
        result = compare_reports(
            baseline=baseline, candidate=candidate, budget=CompareBudget()
        )
        assert result["passed"] is False

    def test_large_budget_allows_regression(self) -> None:
        baseline = EvalReport(suite={}, summary={"score": 1.0}, cases=[])
        candidate = EvalReport(suite={}, summary={"score": 0.5}, cases=[])
        budget = CompareBudget(max_score_regression_pct=60.0)
        result = compare_reports(baseline=baseline, candidate=candidate, budget=budget)
        assert result["passed"] is True

    def test_exactly_at_budget(self) -> None:
        """Regression just within budget boundary passes (<=)."""
        baseline = EvalReport(suite={}, summary={"score": 1.0}, cases=[])
        # Use 0.981 to stay within 2% (1.9% regression) avoiding float imprecision
        candidate = EvalReport(suite={}, summary={"score": 0.981}, cases=[])
        budget = CompareBudget(max_score_regression_pct=2.0)
        result = compare_reports(baseline=baseline, candidate=candidate, budget=budget)
        assert result["passed"] is True


# ============================================================================
# Pack / unpack round-trips
# ============================================================================


def _make_suite_dir(tmp_path: Path, name: str = "roundtrip") -> Path:
    """Helper to create a suite directory."""
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "suite.json").write_text(
        json.dumps({
            "schema_version": 1,
            "name": name,
            "description": "round-trip test",
            "created_at": "2025-01-01T00:00:00Z",
            "scoring": {"json_schema": {"required_keys": ["status"]}},
        }),
        encoding="utf-8",
    )
    cases = [
        {"id": "c1", "input": {"prompt": "a"}, "expected": {"status": "ok"}, "tags": ["fast"]},
        {"id": "c2", "input": {"prompt": "b"}, "expected": "hello", "tags": ["slow"]},
        {"id": "c3", "input": {"prompt": "c"}, "expected": None, "tags": []},
    ]
    (suite_dir / "cases.jsonl").write_text(
        "\n".join(json.dumps(c) for c in cases) + "\n",
        encoding="utf-8",
    )
    return suite_dir


class TestPackRoundTrip:
    def test_create_verify_load(self, tmp_path: Path) -> None:
        suite_dir = _make_suite_dir(tmp_path)
        pack_zip = tmp_path / "suite.zip"

        create_pack(suite_dir=suite_dir, out_zip=pack_zip)
        assert pack_zip.exists()

        # Verify hashes
        result = verify_pack(pack_zip=pack_zip)
        assert result["ok"] is True

        # Load from zip
        suite = load_suite_from_path(pack_zip)
        assert suite.name == "roundtrip"
        assert len(suite.cases) == 3

    def test_load_from_dir(self, tmp_path: Path) -> None:
        suite_dir = _make_suite_dir(tmp_path)
        suite = load_suite_from_path(suite_dir)
        assert suite.name == "roundtrip"

    def test_case_data_preserved(self, tmp_path: Path) -> None:
        suite_dir = _make_suite_dir(tmp_path)
        pack_zip = tmp_path / "suite.zip"
        create_pack(suite_dir=suite_dir, out_zip=pack_zip)

        suite = load_suite_from_path(pack_zip)
        c1 = next(c for c in suite.cases if c.id == "c1")
        assert c1.tags == ["fast"]
        assert c1.expected == {"status": "ok"}

        c3 = next(c for c in suite.cases if c.id == "c3")
        assert c3.expected is None
        assert c3.tags == []

    def test_scoring_config_preserved(self, tmp_path: Path) -> None:
        suite_dir = _make_suite_dir(tmp_path)
        pack_zip = tmp_path / "suite.zip"
        create_pack(suite_dir=suite_dir, out_zip=pack_zip)

        suite = load_suite_from_path(pack_zip)
        assert "json_schema" in suite.scoring
        assert suite.scoring["json_schema"]["required_keys"] == ["status"]

    def test_unsupported_path_raises(self, tmp_path: Path) -> None:
        bad_path = tmp_path / "suite.tar.gz"
        bad_path.write_bytes(b"dummy")
        with pytest.raises(ValueError, match="unsupported_suite_path"):
            load_suite_from_path(bad_path)


# ============================================================================
# End-to-end run with all scorer interactions
# ============================================================================


class TestEndToEndRun:
    def test_mixed_scoring(self, tmp_path: Path) -> None:
        """Test suite with both exact_match and json_required_keys scoring."""
        suite_dir = _make_suite_dir(tmp_path)
        preds = tmp_path / "preds.jsonl"
        preds.write_text(
            "\n".join([
                json.dumps({"id": "c1", "prediction": json.dumps({"status": "ok"})}),
                json.dumps({"id": "c2", "prediction": "hello"}),
                json.dumps({"id": "c3", "prediction": None}),
            ]) + "\n",
            encoding="utf-8",
        )

        suite = load_suite_from_path(suite_dir)
        report = run_suite(suite=suite, predictions_path=preds)
        assert report.summary["cases"] == 3

        # c1: exact_match on dict fails (string vs dict), but json_required_keys scores 1.0
        c1 = next(c for c in report.cases if c["id"] == "c1")
        assert c1["score"] >= 1.0

        # c2: exact_match scores 1.0
        c2 = next(c for c in report.cases if c["id"] == "c2")
        assert c2["score"] == 1.0

        # c3: expected=None, predicted=None -> exact_match 1.0
        c3 = next(c for c in report.cases if c["id"] == "c3")
        assert c3["score"] == 1.0

    def test_missing_prediction(self, tmp_path: Path) -> None:
        """Missing prediction scores 0."""
        suite_dir = _make_suite_dir(tmp_path)
        preds = tmp_path / "preds.jsonl"
        # Only provide prediction for c1, skip c2 and c3
        preds.write_text(
            json.dumps({"id": "c1", "prediction": json.dumps({"status": "ok"})}) + "\n",
            encoding="utf-8",
        )

        suite = load_suite_from_path(suite_dir)
        report = run_suite(suite=suite, predictions_path=preds)

        c2 = next(c for c in report.cases if c["id"] == "c2")
        assert c2["score"] == 0.0


# ============================================================================
# CLI --format and --output flags
# ============================================================================


class TestCLIFormatFlag:
    def test_format_table(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        suite_dir = _make_suite_dir(tmp_path)
        preds = tmp_path / "preds.jsonl"
        preds.write_text(
            json.dumps({"id": "c1", "prediction": "x"}) + "\n"
            + json.dumps({"id": "c2", "prediction": "hello"}) + "\n"
            + json.dumps({"id": "c3", "prediction": None}) + "\n",
            encoding="utf-8",
        )

        rc = main([
            "--format", "table",
            "run", "--suite", str(suite_dir), "--predictions", str(preds),
        ])
        assert rc == EXIT_SUCCESS
        output = capsys.readouterr().out
        assert "Suite: roundtrip" in output
        assert "c1" in output

    def test_format_csv(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        suite_dir = _make_suite_dir(tmp_path)
        preds = tmp_path / "preds.jsonl"
        preds.write_text(
            json.dumps({"id": "c1", "prediction": "x"}) + "\n"
            + json.dumps({"id": "c2", "prediction": "hello"}) + "\n"
            + json.dumps({"id": "c3", "prediction": None}) + "\n",
            encoding="utf-8",
        )

        rc = main([
            "--format", "csv",
            "run", "--suite", str(suite_dir), "--predictions", str(preds),
        ])
        assert rc == EXIT_SUCCESS
        output = capsys.readouterr().out
        assert "id,score,tags" in output

    def test_output_to_file(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        suite_dir = _make_suite_dir(tmp_path)
        preds = tmp_path / "preds.jsonl"
        preds.write_text(
            json.dumps({"id": "c1", "prediction": "x"}) + "\n"
            + json.dumps({"id": "c2", "prediction": "hello"}) + "\n"
            + json.dumps({"id": "c3", "prediction": None}) + "\n",
            encoding="utf-8",
        )
        out_file = tmp_path / "result.json"

        rc = main([
            "--output", str(out_file),
            "run", "--suite", str(suite_dir), "--predictions", str(preds),
        ])
        assert rc == EXIT_SUCCESS
        assert out_file.exists()
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert "summary" in data

        # stdout should be empty when --output is used
        stdout = capsys.readouterr().out
        assert stdout.strip() == ""

    def test_check_deps_table(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main(["--format", "table", "check-deps"])
        assert rc == EXIT_SUCCESS
        output = capsys.readouterr().out
        assert "all_ok" in output

    def test_validate_report_csv(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        report = tmp_path / "report.json"
        report.write_text(
            json.dumps({"suite": {}, "summary": {}, "cases": []}),
            encoding="utf-8",
        )
        rc = main(["--format", "csv", "validate-report", "--report", str(report)])
        assert rc == EXIT_SUCCESS
        output = capsys.readouterr().out
        assert "key,value" in output
