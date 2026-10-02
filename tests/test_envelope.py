"""Report envelope v1 (in-toto Statement v1): shape, canonical form and CLI integration.

The committed JSON Schema (``schemas/report-envelope.v1.json``) is the reference: every
envelope the CLI writes must validate against it, and the dependency-free
``validate_envelope`` must agree with it on valid and invalid documents.
"""

from __future__ import annotations

import copy
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Any

import pytest

from toolkit_eval_harness.cli import main
from toolkit_eval_harness.envelope import (
    PREDICATE_TYPE,
    STATEMENT_TYPE,
    build_statement,
    canonical_json_bytes,
    resource,
    validate_envelope,
    verdict_for_exit_code,
)
from toolkit_eval_harness.pack import create_pack, load_suite_from_path
from toolkit_eval_harness.report import EvalReport

jsonschema = pytest.importorskip("jsonschema")

SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "report-envelope.v1.json"


@pytest.fixture(scope="module")
def validator() -> Any:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    cls = jsonschema.Draft202012Validator
    cls.check_schema(schema)
    return cls(schema, format_checker=cls.FORMAT_CHECKER)


def _suite(tmp_path: Path, *, expected_c2: str = "no") -> Path:
    d = tmp_path / "suite"
    d.mkdir(exist_ok=True)
    (d / "suite.json").write_text(
        json.dumps({"schema_version": 1, "name": "env-demo", "scoring": {}}), encoding="utf-8"
    )
    (d / "cases.jsonl").write_text(
        json.dumps({"id": "c1", "expected": "yes", "tags": ["a"]})
        + "\n"
        + json.dumps({"id": "c2", "expected": expected_c2, "tags": ["b"]})
        + "\n",
        encoding="utf-8",
    )
    return d


def _preds(tmp_path: Path, name: str, c2: str) -> Path:
    p = tmp_path / name
    p.write_text(
        json.dumps({"id": "c1", "prediction": "yes"})
        + "\n"
        + json.dumps({"id": "c2", "prediction": c2})
        + "\n",
        encoding="utf-8",
    )
    return p


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# canonical JSON
# ---------------------------------------------------------------------------


def test_canonical_json_is_sorted_compact_utf8_with_newline() -> None:
    data = canonical_json_bytes({"b": 1, "a": [1, 2], "c": "é"})
    assert data == '{"a":[1,2],"b":1,"c":"é"}\n'.encode()


def test_canonical_json_rejects_nan() -> None:
    with pytest.raises(ValueError):
        canonical_json_bytes({"x": float("nan")})


def test_verdict_mapping() -> None:
    assert verdict_for_exit_code(0) == "pass"
    assert verdict_for_exit_code(1) == "fail"
    for code in (2, 3, 4):
        assert verdict_for_exit_code(code) == "error"


# ---------------------------------------------------------------------------
# run --out
# ---------------------------------------------------------------------------


def test_run_out_writes_valid_canonical_envelope(tmp_path: Path, validator: Any) -> None:
    suite_dir = _suite(tmp_path)
    preds = _preds(tmp_path, "preds.jsonl", "no")
    out = tmp_path / "report.json"
    rc = main(["run", "--suite", str(suite_dir), "--predictions", str(preds), "--out", str(out)])
    assert rc == 0

    raw = out.read_bytes()
    env = json.loads(raw)
    validator.validate(env)
    assert validate_envelope(env) == []
    assert raw == canonical_json_bytes(env), "report file must be canonical JSON"

    assert env["_type"] == STATEMENT_TYPE
    assert env["predicateType"] == PREDICATE_TYPE
    pred = env["predicate"]
    assert pred["kind"] == "eval.run"
    assert pred["verdict"] == "pass" and pred["exit_code"] == 0
    assert pred["tool"]["name"] == "toolkit-eval-harness"
    assert pred["summary"]["cases"] == 2
    assert pred["summary"]["passed"] == 2
    assert pred["summary"]["pass_rate"] == 1.0

    suite = load_suite_from_path(suite_dir)
    assert env["subject"] == [resource("env-demo", suite.content_digest())]
    assert pred["details"]["suite"]["sha256"] == suite.content_digest()
    by_name = {i["name"]: i["digest"]["sha256"] for i in pred["inputs"]}
    assert by_name[str(preds)] == _sha(preds)
    assert [c["id"] for c in pred["details"]["cases"]] == ["c1", "c2"]


def test_run_failing_case_gives_fail_verdict(tmp_path: Path, validator: Any) -> None:
    suite_dir = _suite(tmp_path)
    preds = _preds(tmp_path, "preds.jsonl", "wrong")
    out = tmp_path / "report.json"
    rc = main(["run", "--suite", str(suite_dir), "--predictions", str(preds), "--out", str(out)])
    assert rc == 1
    env = json.loads(out.read_text(encoding="utf-8"))
    validator.validate(env)
    assert env["predicate"]["verdict"] == "fail"
    assert env["predicate"]["exit_code"] == 1
    assert env["predicate"]["summary"]["failed"] == 1


def test_run_envelope_is_reproducible_with_source_date_epoch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1790000000")
    suite_dir = _suite(tmp_path)
    preds = _preds(tmp_path, "preds.jsonl", "no")
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    for out in (a, b):
        main(["run", "--suite", str(suite_dir), "--predictions", str(preds), "--out", str(out)])
    assert a.read_bytes() == b.read_bytes()
    assert json.loads(a.read_text(encoding="utf-8"))["predicate"]["created_at"] == (
        "2026-09-21T14:13:20Z"
    )


def test_suite_digest_is_the_same_for_directory_and_pack(tmp_path: Path) -> None:
    suite_dir = _suite(tmp_path)
    pack = tmp_path / "suite.zip"
    create_pack(suite_dir=suite_dir, out_zip=pack)
    assert load_suite_from_path(suite_dir).content_digest() == (
        load_suite_from_path(pack).content_digest()
    )
    (tmp_path / "other").mkdir()
    changed = _suite(tmp_path / "other", expected_c2="maybe")
    assert load_suite_from_path(changed).content_digest() != (
        load_suite_from_path(suite_dir).content_digest()
    )


def test_run_on_pack_records_pack_file_digest(tmp_path: Path, validator: Any) -> None:
    suite_dir = _suite(tmp_path)
    pack = tmp_path / "suite.zip"
    create_pack(suite_dir=suite_dir, out_zip=pack)
    preds = _preds(tmp_path, "preds.jsonl", "no")
    out = tmp_path / "report.json"
    assert main(["run", "--suite", str(pack), "--predictions", str(preds), "--out", str(out)]) == 0
    env = json.loads(out.read_text(encoding="utf-8"))
    validator.validate(env)
    by_name = {i["name"]: i["digest"]["sha256"] for i in env["predicate"]["inputs"]}
    assert by_name[str(pack)] == _sha(pack)


def test_tampered_pack_writes_error_envelope(tmp_path: Path, validator: Any) -> None:
    suite_dir = _suite(tmp_path)
    pack = tmp_path / "suite.zip"
    create_pack(suite_dir=suite_dir, out_zip=pack)
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(pack) as src, zipfile.ZipFile(tampered, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "cases.jsonl":
                data = data.replace(b'"no"', b'"yes"')
            dst.writestr(item, data)
    preds = _preds(tmp_path, "preds.jsonl", "no")
    out = tmp_path / "report.json"
    rc = main(["run", "--suite", str(tampered), "--predictions", str(preds), "--out", str(out)])
    assert rc == 4
    env = json.loads(out.read_text(encoding="utf-8"))
    validator.validate(env)
    assert env["predicate"]["verdict"] == "error"
    assert env["predicate"]["exit_code"] == 4
    assert env["subject"][0]["digest"]["sha256"] == _sha(tampered)
    assert env["predicate"]["details"]["error"] == "integrity_failure"


def test_legacy_json_flag_keeps_pre_1_0_report(tmp_path: Path) -> None:
    suite_dir = _suite(tmp_path)
    preds = _preds(tmp_path, "preds.jsonl", "no")
    out = tmp_path / "legacy.json"
    rc = main(
        ["run", "--suite", str(suite_dir), "--predictions", str(preds), "--out", str(out),
         "--legacy-json"]
    )
    assert rc == 0
    legacy = json.loads(out.read_text(encoding="utf-8"))
    assert set(legacy) == {"suite", "summary", "cases", "metadata"}


def test_eval_report_from_dict_reads_envelope(tmp_path: Path) -> None:
    suite_dir = _suite(tmp_path)
    preds = _preds(tmp_path, "preds.jsonl", "no")
    out = tmp_path / "report.json"
    main(["run", "--suite", str(suite_dir), "--predictions", str(preds), "--out", str(out)])
    report = EvalReport.from_dict(json.loads(out.read_text(encoding="utf-8")))
    assert report.summary["score"] == 1.0
    assert len(report.cases) == 2
    assert report.suite["name"] == "env-demo"


def test_eval_report_from_dict_rejects_compare_envelope() -> None:
    env = build_statement(
        kind="eval.compare",
        subject=[resource("s", "0" * 64)],
        exit_code=0,
        inputs=[],
        summary={},
        details={},
        tool_version="1.0.0",
    )
    with pytest.raises(ValueError, match="not_a_run_report"):
        EvalReport.from_dict(env)


# ---------------------------------------------------------------------------
# compare --out and validate-report
# ---------------------------------------------------------------------------


def test_compare_reads_envelopes_and_writes_compare_envelope(
    tmp_path: Path, validator: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    suite_dir = _suite(tmp_path)
    base, cand = tmp_path / "base.json", tmp_path / "cand.json"
    main(["run", "--suite", str(suite_dir), "--predictions",
          str(_preds(tmp_path, "p1.jsonl", "no")), "--out", str(base)])
    main(["run", "--suite", str(suite_dir), "--predictions",
          str(_preds(tmp_path, "p2.jsonl", "wrong")), "--out", str(cand)])
    out = tmp_path / "compare.json"
    capsys.readouterr()
    rc = main(["compare", "--baseline", str(base), "--candidate", str(cand), "--out", str(out)])
    assert rc == 1
    env = json.loads(out.read_text(encoding="utf-8"))
    validator.validate(env)
    assert env["predicate"]["kind"] == "eval.compare"
    assert env["predicate"]["verdict"] == "fail"
    assert env["predicate"]["exit_code"] == 1
    suite_sha = load_suite_from_path(suite_dir).content_digest()
    assert env["subject"] == [resource("env-demo", suite_sha)]
    names = [i["name"] for i in env["predicate"]["inputs"]]
    assert names == [str(base), str(cand)]


def test_validate_report_accepts_envelope_and_rejects_inconsistent_verdict(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    suite_dir = _suite(tmp_path)
    out = tmp_path / "report.json"
    main(["run", "--suite", str(suite_dir), "--predictions",
          str(_preds(tmp_path, "p.jsonl", "no")), "--out", str(out)])
    capsys.readouterr()
    assert main(["validate-report", "--report", str(out)]) == 0
    assert json.loads(capsys.readouterr().out)["schema"] == "report-envelope"

    env = json.loads(out.read_text(encoding="utf-8"))
    env["predicate"]["exit_code"] = 1  # verdict still "pass"
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(env), encoding="utf-8")
    assert main(["validate-report", "--report", str(bad)]) == 4


# ---------------------------------------------------------------------------
# validate_envelope agrees with the JSON Schema
# ---------------------------------------------------------------------------


def _good() -> dict[str, Any]:
    return build_statement(
        kind="eval.run",
        subject=[resource("suite", "a" * 64)],
        exit_code=0,
        inputs=[resource("preds.jsonl", "b" * 64)],
        summary={"score": 1.0},
        details={},
        tool_version="1.0.0",
        created_at="2026-09-26T18:00:00Z",
    )


def _mutations() -> list[tuple[str, Any]]:
    def set_path(path: tuple[Any, ...], value: Any) -> Any:
        def apply(doc: dict[str, Any]) -> dict[str, Any]:
            target: Any = doc
            for key in path[:-1]:
                target = target[key]
            if value is _DELETE:
                del target[path[-1]]
            else:
                target[path[-1]] = value
            return doc

        return apply

    return [
        ("wrong _type", set_path(("_type",), "https://in-toto.io/Statement/v0.1")),
        ("empty subject", set_path(("subject",), [])),
        ("short digest", set_path(("subject", 0, "digest", "sha256"), "abc")),
        ("uppercase digest", set_path(("subject", 0, "digest", "sha256"), "A" * 64)),
        ("no subject name", set_path(("subject", 0, "name"), "")),
        ("bad predicateType", set_path(("predicateType",), "https://example.com/x")),
        ("missing details", set_path(("predicate", "details"), _DELETE)),
        ("missing inputs", set_path(("predicate", "inputs"), _DELETE)),
        ("bad verdict", set_path(("predicate", "verdict"), "ok")),
        ("pass with exit 1", set_path(("predicate", "exit_code"), 1)),
        ("negative exit", set_path(("predicate", "exit_code"), -1)),
        ("bad kind", set_path(("predicate", "kind"), "run")),
        ("local time", set_path(("predicate", "created_at"), "2026-09-26T18:00:00+02:00")),
        ("summary not object", set_path(("predicate", "summary"), [])),
        ("tool without version", set_path(("predicate", "tool"), {"name": "x"})),
        ("input without digest", set_path(("predicate", "inputs"), [{"name": "x"}])),
    ]


_DELETE = object()


def test_validate_envelope_accepts_good_document(validator: Any) -> None:
    doc = _good()
    validator.validate(doc)
    assert validate_envelope(doc) == []
    fail = copy.deepcopy(doc)
    fail["predicate"].update({"verdict": "error", "exit_code": 4})
    validator.validate(fail)
    assert validate_envelope(fail) == []


@pytest.mark.parametrize("label,mutate", _mutations(), ids=[m[0] for m in _mutations()])
def test_validate_envelope_agrees_with_schema_on_invalid(
    label: str, mutate: Any, validator: Any
) -> None:
    doc = mutate(copy.deepcopy(_good()))
    schema_errors = list(validator.iter_errors(doc))
    assert schema_errors, f"schema accepted invalid document: {label}"
    assert validate_envelope(doc), f"validate_envelope accepted invalid document: {label}"
