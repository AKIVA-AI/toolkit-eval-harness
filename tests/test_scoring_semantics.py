"""Scoring semantics: fail-closed aggregation, value-level JSON checks, missing predictions.

These tests pin the rules documented in README "Scoring semantics":

- A case passes only if every required scorer passes. There is no "best of" aggregation.
- The JSON scorer compares values wherever the case's ``expected`` object has one.
- A case with no prediction fails, whatever its ``expected`` value.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from toolkit_eval_harness.plugins import _reset_registry, register_scorer
from toolkit_eval_harness.report import EvalReport
from toolkit_eval_harness.runner import run_suite
from toolkit_eval_harness.scoring import JSONSchema, json_required_keys_score
from toolkit_eval_harness.suite import read_suite_dir


def _suite(tmp_path: Path, scoring: dict[str, Any], cases: list[dict[str, Any]]) -> Path:
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "suite.json").write_text(
        json.dumps({"schema_version": 1, "name": "s", "scoring": scoring}), encoding="utf-8"
    )
    (suite_dir / "cases.jsonl").write_text(
        "\n".join(json.dumps(c) for c in cases) + "\n", encoding="utf-8"
    )
    return suite_dir


def _preds(tmp_path: Path, lines: list[dict[str, Any]]) -> Path:
    p = tmp_path / "preds.jsonl"
    p.write_text("".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8")
    return p


def _run(
    tmp_path: Path,
    scoring: dict[str, Any],
    cases: list[dict[str, Any]],
    preds: list[dict[str, Any]],
) -> EvalReport:
    suite = read_suite_dir(_suite(tmp_path, scoring, cases))
    return run_suite(suite=suite, predictions_path=_preds(tmp_path, preds))


@pytest.fixture()
def clean_registry() -> Iterator[None]:
    _reset_registry()
    yield
    _reset_registry()


# ---------------------------------------------------------------------------
# JSON scorer compares values
# ---------------------------------------------------------------------------


class TestJsonScorerValues:
    def test_wrong_value_with_right_keys_is_not_full_score(self) -> None:
        schema = JSONSchema(required_keys=["answer"], optional_keys=[])
        score, meta = json_required_keys_score(
            schema=schema, predicted={"answer": "London"}, expected={"answer": "Paris"}
        )
        assert score < 1.0
        assert "value_mismatch:answer" in meta["reasons"]

    def test_right_value_scores_one(self) -> None:
        schema = JSONSchema(required_keys=["answer"], optional_keys=[])
        score, _ = json_required_keys_score(
            schema=schema, predicted='{"answer": "Paris"}', expected={"answer": "Paris"}
        )
        assert score == 1.0

    def test_expected_key_outside_required_keys_is_still_compared(self) -> None:
        schema = JSONSchema(required_keys=["status"], optional_keys=[])
        score, meta = json_required_keys_score(
            schema=schema,
            predicted={"status": "ok", "total": 3},
            expected={"status": "ok", "total": 4},
        )
        assert score < 1.0
        assert "value_mismatch:total" in meta["reasons"]

    def test_required_key_without_expected_value_is_presence_only(self) -> None:
        schema = JSONSchema(required_keys=["status", "result"], optional_keys=[])
        score, _ = json_required_keys_score(
            schema=schema, predicted={"status": "ok", "result": {}}, expected={"status": "ok"}
        )
        assert score == 1.0

    def test_disallowed_extra_keys_fail(self) -> None:
        schema = JSONSchema(required_keys=["a"], optional_keys=[], allow_extra_keys=False)
        score, _ = json_required_keys_score(schema=schema, predicted={"a": 1, "zzz": 2})
        assert score < 1.0


# ---------------------------------------------------------------------------
# Aggregation: every required scorer must pass
# ---------------------------------------------------------------------------


class TestAggregation:
    def test_wrong_json_value_fails_the_case(self, tmp_path: Path) -> None:
        report = _run(
            tmp_path,
            {"json_schema": {"required_keys": ["answer"]}},
            [{"id": "c1", "expected": {"answer": "Paris"}}],
            [{"id": "c1", "prediction": {"answer": "London"}}],
        )
        case = report.cases[0]
        assert case["passed"] is False
        assert case["score"] < 1.0
        assert report.summary["failed"] == 1

    def test_permissive_plugin_cannot_override_failed_exact(
        self, tmp_path: Path, clean_registry: None
    ) -> None:
        def contains(*, expected: Any, predicted: Any, **_: Any) -> tuple[float, dict[str, Any]]:
            return (1.0 if str(expected) in str(predicted) else 0.0), {}

        register_scorer("contains", contains)
        report = _run(
            tmp_path,
            {"scorers": ["exact", "contains"]},
            [{"id": "c1", "expected": "Paris"}],
            [{"id": "c1", "prediction": "Paris, or maybe Lyon"}],
        )
        case = report.cases[0]
        assert case["plugins"]["contains"]["score"] == 1.0
        assert case["exact"]["match"] is False
        assert case["passed"] is False
        assert case["score"] == 0.0

    def test_plugin_only_suite_is_judged_by_the_plugin(
        self, tmp_path: Path, clean_registry: None
    ) -> None:
        def contains(*, expected: Any, predicted: Any, **_: Any) -> tuple[float, dict[str, Any]]:
            return (1.0 if str(expected) in str(predicted) else 0.0), {}

        register_scorer("contains", contains)
        report = _run(
            tmp_path,
            {"scorers": ["contains"]},
            [{"id": "c1", "expected": "Paris"}],
            [{"id": "c1", "prediction": "It is Paris."}],
        )
        assert report.cases[0]["passed"] is True
        assert report.summary["scorers"] == ["contains"]

    def test_json_schema_and_exact_are_both_required_when_listed(self, tmp_path: Path) -> None:
        report = _run(
            tmp_path,
            {"json_schema": {"required_keys": ["a"]}, "scorers": ["exact"]},
            [{"id": "c1", "expected": {"a": 1}}],
            [{"id": "c1", "prediction": '{"a": 1}'}],
        )
        # JSON scorer passes on the parsed string, exact match does not (str != dict).
        assert report.cases[0]["passed"] is False
        assert report.summary["scorers"] == ["json", "exact"]

    def test_unknown_scorer_fails_closed(self, tmp_path: Path, clean_registry: None) -> None:
        with pytest.raises(ValueError, match="unknown_scorer:nope"):
            _run(
                tmp_path,
                {"scorers": ["nope"]},
                [{"id": "c1", "expected": "x"}],
                [{"id": "c1", "prediction": "x"}],
            )

    def test_crashing_plugin_fails_the_case(self, tmp_path: Path, clean_registry: None) -> None:
        def boom(**_: Any) -> tuple[float, dict[str, Any]]:
            raise RuntimeError("boom")

        register_scorer("boom", boom)
        report = _run(
            tmp_path,
            {"scorers": ["boom"]},
            [{"id": "c1", "expected": "x"}],
            [{"id": "c1", "prediction": "x"}],
        )
        assert report.cases[0]["passed"] is False
        assert report.cases[0]["plugins"]["boom"]["error"] is True


# ---------------------------------------------------------------------------
# Missing predictions fail closed
# ---------------------------------------------------------------------------


class TestMissingPredictions:
    def test_missing_prediction_with_null_expected_fails(self, tmp_path: Path) -> None:
        report = _run(
            tmp_path,
            {},
            [{"id": "c1", "expected": None}, {"id": "c2"}],
            [],
        )
        for case in report.cases:
            assert case["score"] == 0.0
            assert case["passed"] is False
            assert case["missing_prediction"] is True
        assert report.summary["missing_predictions"] == 2
        assert report.summary["score"] == 0.0

    def test_line_without_prediction_field_counts_as_missing(self, tmp_path: Path) -> None:
        report = _run(tmp_path, {}, [{"id": "c1", "expected": None}], [{"id": "c1"}])
        assert report.cases[0]["missing_prediction"] is True
        assert report.cases[0]["passed"] is False

    def test_explicit_null_prediction_is_scored(self, tmp_path: Path) -> None:
        report = _run(
            tmp_path, {}, [{"id": "c1", "expected": None}], [{"id": "c1", "prediction": None}]
        )
        assert report.cases[0]["missing_prediction"] is False
        assert report.cases[0]["passed"] is True

    def test_prediction_line_without_id_is_an_input_error(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="line 1"):
            _run(tmp_path, {}, [{"id": "c1", "expected": "x"}], [{"prediction": "x"}])

    def test_duplicate_prediction_ids_are_an_input_error(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="duplicate_prediction_id:c1"):
            _run(
                tmp_path,
                {},
                [{"id": "c1", "expected": "x"}],
                [{"id": "c1", "prediction": "x"}, {"id": "c1", "prediction": "y"}],
            )

    def test_unknown_prediction_ids_are_counted(self, tmp_path: Path) -> None:
        report = _run(
            tmp_path,
            {},
            [{"id": "c1", "expected": "x"}],
            [{"id": "c1", "prediction": "x"}, {"id": "other", "prediction": "y"}],
        )
        assert report.summary["unknown_predictions"] == 1
        assert report.summary["passed"] == 1


class TestSuiteParsing:
    def test_duplicate_case_ids_are_rejected(self, tmp_path: Path) -> None:
        suite_dir = _suite(
            tmp_path, {}, [{"id": "c1", "expected": "a"}, {"id": "c1", "expected": "b"}]
        )
        with pytest.raises(ValueError, match="duplicate_case_id:c1"):
            read_suite_dir(suite_dir)

    def test_case_without_id_is_rejected(self, tmp_path: Path) -> None:
        suite_dir = _suite(tmp_path, {}, [{"expected": "a"}])
        with pytest.raises(ValueError, match="line 1"):
            read_suite_dir(suite_dir)
