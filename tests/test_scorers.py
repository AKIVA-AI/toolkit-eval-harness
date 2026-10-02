"""Built-in configurable scorers, validated against reference implementations.

Reference values were computed in a python:3.12-slim container:

- SQuAD: the official ``evaluate-v1.1.py`` (as mirrored at
  https://raw.githubusercontent.com/allenai/bi-att-flow/master/squad/evaluate-v1.1.py),
  functions ``normalize_answer``, ``exact_match_score`` and ``f1_score``.
- Levenshtein: ``rapidfuzz.distance.Levenshtein`` 3.14.1, ``distance`` and
  ``normalized_similarity``. "kitten"/"sitting" = 3 is also the textbook example
  (Wikipedia, "Levenshtein distance").
"""

from __future__ import annotations

import json
import math
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from toolkit_eval_harness.cli import main
from toolkit_eval_harness.runner import resolve_scorer_names, run_suite
from toolkit_eval_harness.scorers import (
    BUILTIN_SCORERS,
    DEFAULT_JUDGE_PROMPT,
    cosine_similarity,
    judge_prompt_sha256,
    levenshtein,
    levenshtein_similarity,
    normalize_answer,
    parse_number,
    token_f1,
)
from toolkit_eval_harness.suite import EvalCase, EvalSuite

# (prediction, ground truth, normalize(pred), normalize(truth), EM, F1) from evaluate-v1.1.py
SQUAD_REFERENCE = [
    ("The Quick, brown fox!", "quick brown fox", "quick brown fox", "quick brown fox", True, 1.0),
    ("the cat sat", "cat sat on mat", "cat sat", "cat sat on mat", False, 0.666667),
    ("An apple a day", "apple day", "apple day", "apple day", True, 1.0),
    ("Paris", "paris.", "paris", "paris", True, 1.0),
    ("Denver Broncos", "The Denver Broncos", "denver broncos", "denver broncos", True, 1.0),
    ("", "anything", "", "anything", False, 0.0),
    ("New  York\tCity", "new york", "new york city", "new york", False, 0.8),
    ("1,234", "1234", "1234", "1234", True, 1.0),
]

# (a, b, distance, normalized_similarity) from rapidfuzz 3.14.1
LEVENSHTEIN_REFERENCE = [
    ("kitten", "sitting", 3, 0.571429),
    ("flaw", "lawn", 2, 0.5),
    ("paris", "pariss", 1, 0.833333),
    ("", "abc", 3, 0.0),
    ("abc", "abc", 0, 1.0),
    ("intention", "execution", 5, 0.444444),
]


@pytest.mark.parametrize("pred,truth,npred,ntruth,em,f1", SQUAD_REFERENCE)
def test_squad_normalization_em_and_f1(
    pred: str, truth: str, npred: str, ntruth: str, em: bool, f1: float
) -> None:
    assert normalize_answer(pred) == npred
    assert normalize_answer(truth) == ntruth
    assert (normalize_answer(pred) == normalize_answer(truth)) is em
    assert token_f1(pred, truth) == pytest.approx(f1, abs=1e-6)


@pytest.mark.parametrize("a,b,dist,sim", LEVENSHTEIN_REFERENCE)
def test_levenshtein_matches_rapidfuzz(a: str, b: str, dist: int, sim: float) -> None:
    assert levenshtein(a, b) == dist
    assert levenshtein(b, a) == dist
    assert levenshtein_similarity(a, b) == pytest.approx(sim, abs=1e-6)


def test_cosine_similarity_worked_example() -> None:
    # [1,2,3].[4,5,6] = 32; |a| = sqrt(14), |b| = sqrt(77) -> 32 / sqrt(1078) = 0.974632
    assert cosine_similarity([1, 2, 3], [4, 5, 6]) == pytest.approx(0.974632, abs=1e-6)
    assert cosine_similarity([1, 0], [0, 1]) == 0.0
    with pytest.raises(ValueError):
        cosine_similarity([1.0], [1.0, 2.0])


@pytest.mark.parametrize(
    "value,extract,expected",
    [
        ("42", "full", 42.0),
        ("1,234.5", "full", 1234.5),
        (" -3e2 ", "full", -300.0),
        ("the answer is 42", "full", None),
        ("the answer is 42", "last", 42.0),
        ("3 apples and 5 pears", "first", 3.0),
        ("#### 72", "last", 72.0),
        (7, "full", 7.0),
        (True, "full", None),
        ("nan", "full", None),
    ],
)
def test_parse_number(value: Any, extract: str, expected: float | None) -> None:
    assert parse_number(value, extract) == expected


# ---------------------------------------------------------------------------
# Through run_suite
# ---------------------------------------------------------------------------


def _run(
    tmp_path: Path,
    scorers: list[Any],
    rows: list[tuple[Any, Any]],
    *,
    allow_network: bool = False,
    inputs: list[Any] | None = None,
) -> Any:
    cases = [
        EvalCase(id=f"c{i}", input=(inputs or [None] * len(rows))[i], expected=exp, tags=[])
        for i, (exp, _) in enumerate(rows)
    ]
    suite = EvalSuite(schema_version=1, name="s", description="", created_at="",
                      scoring={"scorers": scorers}, cases=cases)
    preds = tmp_path / "preds.jsonl"
    preds.write_text(
        "".join(json.dumps({"id": f"c{i}", "prediction": p}) + "\n"
                for i, (_, p) in enumerate(rows)),
        encoding="utf-8",
    )
    return run_suite(suite=suite, predictions_path=preds, allow_network_scorers=allow_network)


def _passed(report: Any) -> list[bool]:
    return [c["passed"] for c in report.cases]


def test_normalized_exact_accepts_any_listed_answer(tmp_path: Path) -> None:
    report = _run(tmp_path, ["normalized_exact"], [
        ("Paris", "paris."), (["NYC", "New York City"], "new york city!"), ("Paris", "Lyon"),
    ])
    assert _passed(report) == [True, True, False]


def test_token_f1_threshold(tmp_path: Path) -> None:
    report = _run(tmp_path, [{"name": "token_f1", "threshold": 0.6}],
                  [("cat sat on mat", "the cat sat"), ("cat sat on mat", "dog")])
    assert _passed(report) == [True, False]
    meta = report.cases[0]["scores"]["token_f1"]
    assert meta["metric"] == pytest.approx(2 / 3) and meta["score"] == 1.0
    # Below threshold the score is the raw metric, not 0, so compare still sees partial credit.
    strict = _run(tmp_path, ["token_f1"], [("cat sat on mat", "the cat sat")])
    assert strict.cases[0]["score"] == pytest.approx(2 / 3)
    assert strict.cases[0]["passed"] is False


def test_fuzzy_threshold_and_normalization(tmp_path: Path) -> None:
    report = _run(tmp_path, [{"name": "fuzzy", "threshold": 0.8}],
                  [("Paris", "pariss"), ("kitten", "sitting"), ("New York", "new  york")])
    assert _passed(report) == [True, False, True]
    assert report.cases[1]["score"] == pytest.approx(4 / 7)


def test_regex_from_option_and_from_expected(tmp_path: Path) -> None:
    fixed = _run(tmp_path, [{"name": "regex", "pattern": r"\d{4}-\d{2}-\d{2}"}],
                 [(None, "on 2026-09-26"), (None, "tomorrow")])
    assert _passed(fixed) == [True, False]
    per_case = _run(tmp_path, [{"name": "regex", "mode": "fullmatch", "ignore_case": True}],
                    [("yes|no", "YES"), ("yes|no", "yes please")])
    assert _passed(per_case) == [True, False]


def test_numeric_tolerances(tmp_path: Path) -> None:
    rows = [(3.14159, "3.1416"), (100, "the total is 101"), (100, "#### 100"), (5, "five")]
    exact = _run(tmp_path, [{"name": "numeric", "extract": "last"}], rows)
    assert _passed(exact) == [False, False, True, False]
    loose = _run(tmp_path, [{"name": "numeric", "extract": "last", "abs_tol": 0.001,
                             "rel_tol": 0.02}], rows)
    assert _passed(loose) == [True, True, True, False]
    # math.isclose semantics (PEP 485): |a-b| <= max(rel_tol * max(|a|,|b|), abs_tol)
    assert math.isclose(101, 100, rel_tol=0.02)


def test_numeric_non_numeric_expected_fails_the_case(tmp_path: Path) -> None:
    report = _run(tmp_path, ["numeric"], [("many", "3")])
    assert report.cases[0]["passed"] is False
    assert report.cases[0]["scores"]["numeric"]["error"] is True


def test_json_schema_scorer(tmp_path: Path) -> None:
    pytest.importorskip("jsonschema")
    schema = {"type": "object", "required": ["answer"],
              "properties": {"answer": {"type": "string"}, "confidence":
                             {"type": "number", "minimum": 0, "maximum": 1}}}
    report = _run(tmp_path, [{"name": "json_schema", "schema": schema}], [
        (None, '{"answer": "Paris", "confidence": 0.9}'),
        (None, {"answer": "Paris", "confidence": 1.5}),
        (None, '{"confidence": 0.2}'),
        (None, "not json"),
    ])
    assert _passed(report) == [True, False, False, False]
    assert "1.5 is greater than the maximum of 1" in report.cases[1]["scores"]["json_schema"][
        "errors"][0]


def test_json_schema_rejects_invalid_schema(tmp_path: Path) -> None:
    pytest.importorskip("jsonschema")
    with pytest.raises(ValueError, match="json_schema schema"):
        _run(tmp_path, [{"name": "json_schema", "schema": {"type": "banana"}}], [(None, "{}")])


def test_all_scorers_must_pass(tmp_path: Path) -> None:
    report = _run(tmp_path, ["exact", "normalized_exact"], [("Paris", "paris")])
    assert report.cases[0]["passed"] is False
    assert report.cases[0]["scores"]["normalized_exact"]["score"] == 1.0


def test_labels_allow_the_same_scorer_twice(tmp_path: Path) -> None:
    report = _run(tmp_path, [
        {"name": "regex", "label": "has_digit", "pattern": r"\d"},
        {"name": "regex", "label": "short", "pattern": r"^.{0,5}$"},
    ], [(None, "a1"), (None, "a1bcdefg")])
    assert _passed(report) == [True, False]
    assert resolve_scorer_names({"scorers": [{"name": "regex", "label": "x", "pattern": "a"}]}) \
        == ["x"]


@pytest.mark.parametrize(
    "scorers,match",
    [
        ([{"name": "fuzzy", "treshold": 0.9}], "does not accept"),
        ([{"name": "fuzzy", "threshold": 2}], "threshold"),
        ([{"name": "regex", "pattern": "("}], "regex pattern"),
        ([{"name": "exact", "foo": 1}], "takes no options"),
        ([{"label": "x"}], "need a 'name'"),
        ([{"name": "regex", "label": "r", "pattern": "a"},
          {"name": "regex", "label": "r", "pattern": "b"}], "duplicate scorer label"),
    ],
)
def test_bad_scorer_config_is_an_input_error(
    tmp_path: Path, scorers: list[Any], match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        _run(tmp_path, scorers, [("a", "a")])


# ---------------------------------------------------------------------------
# Network scorers: off by default, recorded when on
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_litellm(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    calls: dict[str, Any] = {"completion": [], "embedding": []}

    def completion(**kwargs: Any) -> Any:
        calls["completion"].append(kwargs)
        prompt = kwargs["messages"][0]["content"]
        verdict = 1 if "Answer to grade:\nParis" in prompt else 0
        content = f'Sure. {{"score": {verdict}, "reason": "checked"}}'
        return {"choices": [{"message": {"content": content}}]}

    def embedding(**kwargs: Any) -> Any:
        calls["embedding"].append(kwargs)
        vectors = {"Paris": [1.0, 0.0], "paris": [0.9, 0.1], "Lyon": [0.0, 1.0]}
        return types.SimpleNamespace(
            data=[{"embedding": vectors.get(t, [0.5, 0.5])} for t in kwargs["input"]]
        )

    monkeypatch.setitem(sys.modules, "litellm",
                        types.SimpleNamespace(completion=completion, embedding=embedding))
    return calls


@pytest.mark.parametrize("name", ["llm_judge", "embedding"])
def test_network_scorers_are_off_by_default(
    tmp_path: Path, fake_litellm: dict[str, Any], name: str
) -> None:
    with pytest.raises(ValueError, match="network_scorer_disabled"):
        _run(tmp_path, [{"name": name, "model": "m"}], [("Paris", "Paris")])
    assert fake_litellm["completion"] == [] and fake_litellm["embedding"] == []
    assert BUILTIN_SCORERS[name].network is True


def test_llm_judge_records_model_and_prompt(tmp_path: Path, fake_litellm: dict[str, Any]) -> None:
    report = _run(tmp_path, [{"name": "llm_judge", "model": "openai/gpt-x"}],
                  [("Paris", "Paris"), ("Paris", "Lyon")], allow_network=True,
                  inputs=["Capital of France?", "Capital of France?"])
    assert _passed(report) == [True, False]
    meta = report.cases[0]["scores"]["llm_judge"]
    assert meta["model"] == "openai/gpt-x"
    assert "Capital of France?" in meta["prompt"] and "Reference answer:\nParis" in meta["prompt"]
    assert meta["raw_response"].startswith("Sure.")
    assert meta["reason"] == "checked"
    config = report.summary["scorer_config"]["llm_judge"]
    assert config["model"] == "openai/gpt-x"
    assert config["prompt"] == DEFAULT_JUDGE_PROMPT
    assert config["prompt_sha256"] == judge_prompt_sha256(DEFAULT_JUDGE_PROMPT)
    assert config["temperature"] == 0.0
    assert fake_litellm["completion"][0]["temperature"] == 0.0


def test_llm_judge_unparseable_reply_fails_the_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = types.SimpleNamespace(
        completion=lambda **_: {"choices": [{"message": {"content": "looks good to me"}}]}
    )
    monkeypatch.setitem(sys.modules, "litellm", fake)
    report = _run(tmp_path, [{"name": "llm_judge", "model": "m"}], [("a", "a")],
                  allow_network=True)
    assert report.cases[0]["passed"] is False
    assert report.cases[0]["scores"]["llm_judge"]["error"] is True


def test_embedding_scorer(tmp_path: Path, fake_litellm: dict[str, Any]) -> None:
    report = _run(tmp_path, [{"name": "embedding", "model": "e", "threshold": 0.9}],
                  [("Paris", "paris"), ("Paris", "Lyon")], allow_network=True)
    assert _passed(report) == [True, False]
    sim = cosine_similarity([1.0, 0.0], [0.9, 0.1])
    assert report.cases[0]["scores"]["embedding"]["metric"] == pytest.approx(sim)
    assert fake_litellm["embedding"][0]["model"] == "e"


def test_cli_allow_network_scorers_flag(
    tmp_path: Path, fake_litellm: dict[str, Any]
) -> None:
    suite = tmp_path / "suite"
    suite.mkdir()
    (suite / "suite.json").write_text(json.dumps(
        {"name": "judge", "scoring": {"scorers": [{"name": "llm_judge", "model": "m"}]}}
    ), encoding="utf-8")
    (suite / "cases.jsonl").write_text(
        json.dumps({"id": "c1", "input": "Capital?", "expected": "Paris"}) + "\n",
        encoding="utf-8",
    )
    preds = tmp_path / "p.jsonl"
    preds.write_text(json.dumps({"id": "c1", "prediction": "Paris"}) + "\n", encoding="utf-8")
    assert main(["run", "--suite", str(suite), "--predictions", str(preds)]) == 2
    out = tmp_path / "r.json"
    assert main(["run", "--suite", str(suite), "--predictions", str(preds), "--out", str(out),
                 "--allow-network-scorers"]) == 0
    pred = json.loads(out.read_text(encoding="utf-8"))["predicate"]
    assert pred["summary"]["scorers"] == ["llm_judge"]
    judge = pred["details"]["scorer_config"]["llm_judge"]
    assert judge["model"] == "m" and judge["prompt"] == DEFAULT_JUDGE_PROMPT
    assert "Capital?" in pred["details"]["cases"][0]["scores"]["llm_judge"]["prompt"]
