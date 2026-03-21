"""Adversarial and safety tests.

Covers:
- Injection strings and boundary inputs do not crash scorers
- Scores are always in [0.0, 1.0] regardless of input type
- Score manipulation via content tricks is not possible
- Adversarial prediction file formats (blanks, duplicates, missing ID, path traversal)
- Documented behavior for invalid prediction lines
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from toolkit_eval_harness.pack import load_suite_from_path
from toolkit_eval_harness.runner import run_suite
from toolkit_eval_harness.scoring import (
    JSONSchema,
    exact_match_score,
    json_required_keys_score,
)

# ============================================================================
# Helpers
# ============================================================================


def _make_adversarial_suite(tmp_path: Path, cases: list[dict[str, Any]]) -> Path:
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "suite.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "adversarial",
                "description": "adversarial test suite",
                "created_at": "2025-01-01T00:00:00Z",
                "scoring": {},
            }
        ),
        encoding="utf-8",
    )
    (suite_dir / "cases.jsonl").write_text(
        "\n".join(json.dumps(c) for c in cases) + "\n",
        encoding="utf-8",
    )
    return suite_dir


def _write_preds(tmp_path: Path, preds: list[dict[str, Any]]) -> Path:
    path = tmp_path / "preds.jsonl"
    content = "\n".join(json.dumps(p) for p in preds)
    path.write_text(content + "\n" if content else "\n", encoding="utf-8")
    return path


# ============================================================================
# Scorer: injection strings and large inputs
# ============================================================================


INJECTION_STRINGS = [
    "<script>alert(1)</script>",
    "' OR 1=1; DROP TABLE cases; --",
    "\x00null\x00byte",
    "../../../etc/passwd",
    "{{7*7}}",
    "\u202e\u0041\u0042\u0043",  # RTL override
    "\ufeff",  # Unicode BOM
]


class TestScorerAdversarialInputs:
    @pytest.mark.parametrize("attack", INJECTION_STRINGS)
    def test_exact_match_injection_scores_zero(self, attack: str) -> None:
        score, _ = exact_match_score(expected="safe_value", predicted=attack)
        assert score == 0.0

    @pytest.mark.parametrize("attack", INJECTION_STRINGS)
    def test_exact_match_injection_does_not_crash(self, attack: str) -> None:
        score, _ = exact_match_score(expected=attack, predicted=attack)
        assert 0.0 <= score <= 1.0

    @pytest.mark.parametrize("attack", INJECTION_STRINGS)
    def test_json_scorer_injection_in_value_does_not_crash(self, attack: str) -> None:
        schema = JSONSchema(required_keys=["status"], optional_keys=[], allow_extra_keys=True)
        score, _ = json_required_keys_score(schema=schema, predicted={"status": attack})
        assert 0.0 <= score <= 1.0

    def test_very_long_string_scores_correctly(self) -> None:
        long_string = "A" * 100_000
        score, _ = exact_match_score(expected="short", predicted=long_string)
        assert score == 0.0

    def test_deeply_nested_json_does_not_crash(self) -> None:
        nested: Any = {"leaf": "value"}
        for _ in range(50):
            nested = {"child": nested}
        schema = JSONSchema(required_keys=["leaf"], optional_keys=[], allow_extra_keys=True)
        score, _ = json_required_keys_score(schema=schema, predicted=nested)
        assert 0.0 <= score <= 1.0


# ============================================================================
# Score boundary integrity
# ============================================================================


class TestScoreBoundaryIntegrity:
    """Scores must always be in [0.0, 1.0] regardless of input type combination."""

    def test_exact_match_mixed_types(self) -> None:
        pairs: list[tuple[Any, Any]] = [
            (None, 0),
            (0, None),
            ([], {}),
            (True, 1),
            (False, 0),
            (1.0, 1),
            ("", 0),
            ({"a": 1}, {"a": 2}),
        ]
        for expected, predicted in pairs:
            score, _ = exact_match_score(expected=expected, predicted=predicted)
            assert 0.0 <= score <= 1.0, f"Out of range for ({expected!r}, {predicted!r})"

    def test_json_scorer_adversarial_predictions(self) -> None:
        schema = JSONSchema(required_keys=["a", "b", "c"], optional_keys=[], allow_extra_keys=True)
        adversarial: list[Any] = [
            None,
            42,
            [],
            "not json",
            "{broken",
            '{"a": 1}',
            {"a": 1, "b": 2, "c": 3},
            {},
        ]
        for pred in adversarial:
            score, _ = json_required_keys_score(schema=schema, predicted=pred)
            assert 0.0 <= score <= 1.0, f"Out of range for predicted={pred!r}"


# ============================================================================
# Score manipulation resistance
# ============================================================================


class TestScoreManipulationResistance:
    """Predictions cannot inflate their score through content tricks."""

    def test_prediction_claiming_key_via_string_does_not_score(self) -> None:
        """A string mentioning the key name does not satisfy json_required_keys."""
        schema = JSONSchema(required_keys=["secret_key"], optional_keys=[], allow_extra_keys=True)
        score, _ = json_required_keys_score(
            schema=schema,
            predicted='{"__claim__": "I have secret_key", "secret_key_typo": 1}',
        )
        assert score == 0.0

    def test_python_repr_of_dict_does_not_match_dict(self) -> None:
        """Python repr string of expected dict does not equal the dict itself."""
        expected = {"key": "value"}
        predicted = str(expected)  # "{'key': 'value'}"
        score, _ = exact_match_score(expected=expected, predicted=predicted)
        assert score == 0.0

    def test_json_array_at_root_cannot_satisfy_required_keys(self) -> None:
        """A JSON array (not object) scores 0.0 for any required keys schema."""
        schema = JSONSchema(required_keys=["status"], optional_keys=[], allow_extra_keys=True)
        score, _ = json_required_keys_score(schema=schema, predicted='["status", "ok"]')
        assert score == 0.0

    def test_empty_required_keys_scores_one_for_any_object(self) -> None:
        """Schema with no required keys scores 1.0 for any object — expected and documented."""
        schema = JSONSchema(required_keys=[], optional_keys=[], allow_extra_keys=True)
        score, _ = json_required_keys_score(schema=schema, predicted={"anything": "here"})
        assert score == 1.0


# ============================================================================
# Runner: adversarial prediction file formats
# ============================================================================


class TestRunnerAdversarialPredictions:
    def test_injection_string_in_prediction_scores_zero(self, tmp_path: Path) -> None:
        suite_dir = _make_adversarial_suite(
            tmp_path,
            [{"id": "c1", "input": {"prompt": "x"}, "expected": "safe", "tags": []}],
        )
        preds = _write_preds(tmp_path, [{"id": "c1", "prediction": "<script>alert(1)</script>"}])
        suite = load_suite_from_path(suite_dir)
        report = run_suite(suite=suite, predictions_path=preds)
        assert report.cases[0]["score"] == 0.0

    def test_very_long_prediction_does_not_crash_runner(self, tmp_path: Path) -> None:
        suite_dir = _make_adversarial_suite(
            tmp_path,
            [{"id": "c1", "input": {"prompt": "x"}, "expected": "expected_value", "tags": []}],
        )
        preds = _write_preds(tmp_path, [{"id": "c1", "prediction": "X" * 50_000}])
        suite = load_suite_from_path(suite_dir)
        report = run_suite(suite=suite, predictions_path=preds)
        assert report.cases[0]["score"] == 0.0

    def test_blank_lines_in_predictions_file_are_skipped(self, tmp_path: Path) -> None:
        suite_dir = _make_adversarial_suite(
            tmp_path,
            [{"id": "c1", "input": {"prompt": "x"}, "expected": "hello", "tags": []}],
        )
        preds_path = tmp_path / "preds.jsonl"
        preds_path.write_text(
            "\n\n" + json.dumps({"id": "c1", "prediction": "hello"}) + "\n\n",
            encoding="utf-8",
        )
        suite = load_suite_from_path(suite_dir)
        report = run_suite(suite=suite, predictions_path=preds_path)
        assert report.cases[0]["score"] == 1.0

    def test_duplicate_prediction_ids_last_entry_wins(self, tmp_path: Path) -> None:
        suite_dir = _make_adversarial_suite(
            tmp_path,
            [{"id": "c1", "input": {"prompt": "x"}, "expected": "second", "tags": []}],
        )
        preds_path = tmp_path / "preds.jsonl"
        preds_path.write_text(
            json.dumps({"id": "c1", "prediction": "first"}) + "\n"
            + json.dumps({"id": "c1", "prediction": "second"}) + "\n",
            encoding="utf-8",
        )
        suite = load_suite_from_path(suite_dir)
        report = run_suite(suite=suite, predictions_path=preds_path)
        assert report.cases[0]["score"] == 1.0

    def test_path_traversal_id_in_predictions_is_ignored(self, tmp_path: Path) -> None:
        """Prediction IDs that look like path traversal attempts are treated as unknown IDs."""
        suite_dir = _make_adversarial_suite(
            tmp_path,
            [{"id": "c1", "input": {"prompt": "x"}, "expected": "hello", "tags": []}],
        )
        preds = _write_preds(
            tmp_path,
            [
                {"id": "c1", "prediction": "hello"},
                {"id": "../../etc/passwd", "prediction": "should be ignored"},
            ],
        )
        suite = load_suite_from_path(suite_dir)
        report = run_suite(suite=suite, predictions_path=preds)
        assert len(report.cases) == 1
        assert report.cases[0]["score"] == 1.0

    def test_extra_prediction_ids_not_in_suite_are_ignored(self, tmp_path: Path) -> None:
        suite_dir = _make_adversarial_suite(
            tmp_path,
            [{"id": "c1", "input": {"prompt": "x"}, "expected": "hello", "tags": []}],
        )
        preds = _write_preds(
            tmp_path,
            [
                {"id": "c1", "prediction": "hello"},
                {"id": "injected_case", "prediction": "should not appear in report"},
            ],
        )
        suite = load_suite_from_path(suite_dir)
        report = run_suite(suite=suite, predictions_path=preds)
        assert len(report.cases) == 1

    def test_empty_predictions_file_scores_all_zero(self, tmp_path: Path) -> None:
        suite_dir = _make_adversarial_suite(
            tmp_path,
            [
                {"id": "c1", "input": {"prompt": "a"}, "expected": "x", "tags": []},
                {"id": "c2", "input": {"prompt": "b"}, "expected": "y", "tags": []},
            ],
        )
        preds = _write_preds(tmp_path, [])
        suite = load_suite_from_path(suite_dir)
        report = run_suite(suite=suite, predictions_path=preds)
        assert all(c["score"] == 0.0 for c in report.cases)
        assert report.summary["score"] == 0.0

    def test_prediction_missing_id_field_raises_key_error(self, tmp_path: Path) -> None:
        """Documented behavior: prediction line without 'id' raises KeyError.
        Future hardening: consider graceful skip with a warning."""
        suite_dir = _make_adversarial_suite(
            tmp_path,
            [{"id": "c1", "input": {"prompt": "x"}, "expected": "hello", "tags": []}],
        )
        preds_path = tmp_path / "preds.jsonl"
        preds_path.write_text(
            json.dumps({"prediction": "no_id_field"}) + "\n",
            encoding="utf-8",
        )
        suite = load_suite_from_path(suite_dir)
        with pytest.raises(KeyError):
            run_suite(suite=suite, predictions_path=preds_path)
