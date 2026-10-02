"""Import results produced by other eval tools as normalized :class:`EvalReport` objects.

Supported sources (formats verified against files produced by the tools themselves; the
fixtures in ``tests/fixtures/importers/`` were generated as described in their README):

- **promptfoo** ``promptfoo eval -o results.json`` (results ``version`` 3; tested with
  promptfoo 0.123.1).
- **Inspect AI** eval logs: ``.json`` logs (``--log-format json``) and ``.eval`` logs (a zip
  archive; tested with inspect_ai 0.3.270). Recent ``.eval`` logs compress members with
  Zstandard, which the standard library can read only from Python 3.14; on older Pythons
  install the ``inspect`` extra (``zstandard``), or convert the log with
  ``inspect log convert --to json``.
- **DeepEval** test-run JSON, as saved when ``DEEPEVAL_RESULTS_FOLDER`` is set (tested with
  deepeval 4.2.6).

Normalization rules (all importers):

- One case per test / sample. The case ``score`` is the lowest score among the selected
  metrics (fail closed, like ``run``), and ``passed`` follows the source tool's own verdict
  where it has one (promptfoo ``success``, DeepEval ``success``); Inspect has no verdict, so a
  sample passes only when every selected scorer's value is at least 1.0.
- Anything the source marks as an error, and any expected sample that has no result, fails
  with score 0.0.
- ``suite.sha256`` is a digest of each case's id and *inputs* (promptfoo vars and assertions,
  Inspect input and target, DeepEval input, expected output and context), not its outputs.
  Two runs of the same tests therefore share a digest, and ``compare`` can check that a
  baseline and a candidate were produced from the same tests.
"""

from __future__ import annotations

import json
import struct
import zipfile
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .envelope import sha256_json
from .report import EvalReport

SOURCES = ("promptfoo", "inspect", "deepeval")

_ZSTD_METHOD = 93  # ZIP compression method id for Zstandard (APPNOTE.TXT 4.4.5)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _scalar_tags(metadata: Any) -> list[str]:
    """``key:value`` tags from scalar metadata entries (keys starting with _ are skipped)."""
    if not isinstance(metadata, dict):
        return []
    tags = []
    for key in sorted(metadata):
        value = metadata[key]
        if str(key).startswith("_") or isinstance(value, (dict, list)) or value is None:
            continue
        tags.append(f"{key}:{value}")
    return tags


def _finite(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        f = float(value)
        return f if f == f and f not in (float("inf"), float("-inf")) else None
    return None


def _build_report(
    *,
    source: str,
    name: str,
    cases: list[dict[str, Any]],
    identity: dict[str, Any],
    source_info: dict[str, Any],
    scorers: list[str],
) -> EvalReport:
    ids = [c["id"] for c in cases]
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(f"duplicate_case_id:{','.join(dupes)} in {source} results")
    digest = sha256_json([[cid, identity[cid]] for cid in sorted(identity)])
    n = len(cases)
    passed = sum(1 for c in cases if c["passed"])
    summary = {
        "cases": n,
        "score": (sum(c["score"] for c in cases) / n) if n else 0.0,
        "passed": passed,
        "failed": n - passed,
        "missing_predictions": sum(1 for c in cases if c.get("missing_prediction")),
        "unknown_predictions": 0,
        "scorers": scorers,
    }
    suite = {
        "name": name,
        "source": source_info,
        "cases_count": n,
        "sha256": digest,
    }
    return EvalReport(suite=suite, summary=summary, cases=cases)


# ---------------------------------------------------------------------------
# promptfoo
# ---------------------------------------------------------------------------


def import_promptfoo(path: Path, *, provider: str | None = None) -> EvalReport:
    """Normalize a promptfoo ``results.json`` (``promptfoo eval -o results.json``).

    Case ids are the test descriptions when every test has a unique one, otherwise
    ``test-<testIdx>``. When the file holds several prompts or providers (and no *provider*
    filter is given), ``@p<promptIdx>`` and ``@<provider>`` are appended so each row stays
    distinct. Tags: ``provider:<id>`` plus ``key:value`` for scalar test metadata.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("invalid_promptfoo_results:expected a JSON object")
    block = data.get("results")
    rows = block.get("results") if isinstance(block, dict) else block
    if not isinstance(rows, list):
        raise ValueError("invalid_promptfoo_results:no results.results array")

    def provider_id(row: dict[str, Any]) -> str:
        prov = row.get("provider")
        if isinstance(prov, dict):
            return str(prov.get("label") or prov.get("id") or "")
        return str(prov or "")

    def provider_names(row: dict[str, Any]) -> set[str]:
        prov = row.get("provider")
        if isinstance(prov, dict):
            return {str(prov.get(k)) for k in ("id", "label") if prov.get(k)}
        return {str(prov)} if prov else set()

    rows = [r for r in rows if isinstance(r, dict)]
    if provider is not None:
        matched = [r for r in rows if provider in provider_names(r)]
        if not matched:
            found = sorted({provider_id(r) for r in rows})
            raise ValueError(f"unknown_provider:{provider} (results contain: {found})")
        rows = matched

    tests: dict[int, dict[str, Any]] = {}
    for r in rows:
        idx = r.get("testIdx")
        if not isinstance(idx, int):
            raise ValueError("invalid_promptfoo_results:row without integer testIdx")
        tests.setdefault(idx, r.get("testCase") or {})
    descriptions = [str(tc.get("description") or "") for tc in tests.values()]
    use_desc = all(descriptions) and len(set(descriptions)) == len(descriptions)
    multi_prompt = len({r.get("promptIdx") for r in rows}) > 1
    multi_provider = len({provider_id(r) for r in rows}) > 1

    cases: list[dict[str, Any]] = []
    identity: dict[str, Any] = {}
    for r in sorted(rows, key=lambda x: (x["testIdx"], x.get("promptIdx") or 0, provider_id(x))):
        tc = tests[r["testIdx"]]
        case_id = str(tc.get("description")) if use_desc else f"test-{r['testIdx']}"
        if multi_prompt:
            case_id += f"@p{r.get('promptIdx')}"
        if multi_provider:
            case_id += f"@{provider_id(r)}"
        score = _finite(r.get("score"))
        grading = _as_dict(r.get("gradingResult"))
        is_error = r.get("failureReason") == 2 or (bool(r.get("error")) and not grading)
        passed = r.get("success") is True and not is_error and score is not None
        case: dict[str, Any] = {
            "id": case_id,
            "score": 0.0 if (score is None or is_error) else score,
            "passed": passed,
            "tags": [f"provider:{provider_id(r)}", *_scalar_tags(tc.get("metadata"))],
            "missing_prediction": False,
            "source": {"testIdx": r["testIdx"], "promptIdx": r.get("promptIdx"),
                       "provider": provider_id(r)},
        }
        if grading.get("reason"):
            case["reason"] = str(grading["reason"])
        if is_error:
            case["error"] = str(r.get("error") or "error")
        cases.append(case)
        identity[case_id] = {"vars": tc.get("vars"), "assert": tc.get("assert")}

    meta = _as_dict(data.get("metadata"))
    config = _as_dict(data.get("config"))
    return _build_report(
        source="promptfoo",
        name=str(config.get("description") or "promptfoo-eval"),
        cases=cases,
        identity=identity,
        source_info={
            "tool": "promptfoo",
            "version": meta.get("promptfooVersion"),
            "eval_id": data.get("evalId"),
            "providers": sorted({provider_id(r) for r in rows}),
        },
        scorers=["promptfoo"],
    )


# ---------------------------------------------------------------------------
# Inspect AI
# ---------------------------------------------------------------------------


def inspect_value_to_float(value: Any) -> float | None:
    """Map an Inspect score value to a float, as ``inspect_ai.scorer.value_to_float()`` does.

    ``"C"`` 1.0, ``"P"`` 0.5, ``"I"``/``"N"`` 0.0; numbers and booleans as floats; the strings
    yes/true and no/false (any case) 1.0 and 0.0; numeric strings as floats. Returns None
    where Inspect would warn and use 0.0 (lists, dicts, other strings) so the caller can flag
    the case.
    """
    if value == "C":
        return 1.0
    if value == "P":
        return 0.5
    if value in ("I", "N"):
        return 0.0
    if isinstance(value, (bool, int, float)):
        return _finite(value)
    if isinstance(value, str):
        low = value.lower()
        if low in ("yes", "true"):
            return 1.0
        if low in ("no", "false"):
            return 0.0
        try:
            f = float(low)
        except ValueError:
            return None
        return _finite(f)
    return None


def _read_zip_member(zf: zipfile.ZipFile, fh: Any, name: str) -> bytes:
    info = zf.getinfo(name)
    try:
        return zf.read(name)  # Python 3.14+ reads Zstandard members natively (PEP 784)
    except NotImplementedError:
        if info.compress_type != _ZSTD_METHOD:
            raise ValueError(
                f"invalid_eval_log:unsupported compression {info.compress_type} for {name}"
            ) from None
    try:
        import zstandard  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - depends on the environment
        raise ValueError(
            "zstd_required:this .eval log is Zstandard-compressed; install "
            "'toolkit-eval-harness[inspect]' (zstandard) or convert it with "
            "'inspect log convert --to json'"
        ) from exc
    fh.seek(info.header_offset)
    header = fh.read(30)
    if header[:4] != b"PK\x03\x04":
        raise ValueError(f"invalid_eval_log:bad local header for {name}")
    name_len, extra_len = struct.unpack("<HH", header[26:30])
    fh.seek(info.header_offset + 30 + name_len + extra_len)
    raw = fh.read(info.compress_size)
    data = zstandard.ZstdDecompressor().decompress(raw, max_output_size=info.file_size)
    if zlib.crc32(data) != info.CRC:
        raise ValueError(f"invalid_eval_log:CRC mismatch for {name}")
    return bytes(data)


def _load_inspect(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if path.suffix.lower() == ".json":
        log = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(log, dict):
            raise ValueError("invalid_eval_log:expected a JSON object")
        return log, [s for s in log.get("samples") or [] if isinstance(s, dict)]
    with path.open("rb") as fh, zipfile.ZipFile(fh) as zf:
        names = zf.namelist()
        if "header.json" not in names:
            raise ValueError("invalid_eval_log:no header.json in .eval archive")
        header = json.loads(_read_zip_member(zf, fh, "header.json"))
        samples = [
            json.loads(_read_zip_member(zf, fh, n))
            for n in names
            if n.startswith("samples/") and n.endswith(".json")
        ]
    return header, samples


def import_inspect(path: Path, *, scorer: str | None = None) -> EvalReport:
    """Normalize an Inspect AI eval log (``.eval`` or ``.json``).

    One case per sample id; several epochs are reduced by the mean per scorer (Inspect's
    default reducer). Samples listed in ``eval.dataset.sample_ids`` but absent from the log,
    samples with an ``error``, and samples missing a selected scorer fail with score 0.0.
    Tags: ``key:value`` for scalar sample metadata.
    """
    header, samples = _load_inspect(path)
    ev = _as_dict(header.get("eval"))
    declared = [s.get("name") for s in ev.get("scorers") or [] if isinstance(s, dict)]
    seen_scorers = sorted({k for s in samples for k in (s.get("scores") or {})})
    available = [str(n) for n in declared if n] or seen_scorers
    if scorer is not None:
        if scorer not in available and scorer not in seen_scorers:
            raise ValueError(f"unknown_scorer:{scorer} (log has: {available})")
        selected = [scorer]
    else:
        selected = available
    if not selected:
        raise ValueError("invalid_eval_log:no scorers in log")

    by_id: dict[str, list[dict[str, Any]]] = {}
    for s in samples:
        by_id.setdefault(str(s.get("id")), []).append(s)
    dataset = _as_dict(ev.get("dataset"))
    expected_ids = [str(i) for i in dataset.get("sample_ids") or []]
    all_ids = list(dict.fromkeys([*expected_ids, *sorted(by_id)]))

    cases: list[dict[str, Any]] = []
    identity: dict[str, Any] = {}
    for sid in all_ids:
        epochs = sorted(by_id.get(sid, []), key=lambda s: s.get("epoch") or 0)
        if not epochs:
            cases.append({"id": sid, "score": 0.0, "passed": False, "tags": [],
                          "missing_prediction": True})
            identity[sid] = None
            continue
        first = epochs[0]
        identity[sid] = {"input": first.get("input"), "target": first.get("target")}
        case: dict[str, Any] = {
            "id": sid,
            "tags": _scalar_tags(first.get("metadata")),
            "missing_prediction": False,
            "epochs": len(epochs),
        }
        errors = [str(e.get("error")) for e in epochs if e.get("error")]
        per_scorer: dict[str, float] = {}
        problems: list[str] = []
        for name in selected:
            values = []
            for e in epochs:
                raw = (e.get("scores") or {}).get(name)
                value = inspect_value_to_float(raw.get("value")) if isinstance(raw, dict) else None
                if value is None:
                    problems.append(f"{name}:epoch{e.get('epoch')}")
                    value = 0.0
                values.append(value)
            per_scorer[name] = sum(values) / len(values)
        case_score = min(per_scorer.values())
        passed = not errors and not problems and all(v >= 1.0 for v in per_scorer.values())
        case["scores"] = per_scorer
        if errors:
            case["error"] = errors[0]
            case_score = 0.0
        if problems:
            case["unscored"] = problems
        case["score"] = case_score
        case["passed"] = passed
        cases.append(case)

    packages = _as_dict(ev.get("packages"))
    return _build_report(
        source="inspect",
        name=str(ev.get("task") or "inspect-eval"),
        cases=cases,
        identity=identity,
        source_info={
            "tool": "inspect_ai",
            "version": packages.get("inspect_ai"),
            "model": ev.get("model"),
            "status": header.get("status"),
            "eval_id": ev.get("eval_id"),
        },
        scorers=selected,
    )


# ---------------------------------------------------------------------------
# DeepEval
# ---------------------------------------------------------------------------


def import_deepeval(path: Path, *, metric: str | None = None) -> EvalReport:
    """Normalize a DeepEval test-run JSON (the file saved via ``DEEPEVAL_RESULTS_FOLDER``).

    One case per test case (``testCases`` and ``conversationalTestCases``), id = test case
    ``name``. ``passed`` is DeepEval's ``success`` (or the selected metric's ``success``); a
    metric with an ``error`` or no score fails the case. Tags are the test case's ``tags``.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("testCases"), list):
        raise ValueError("invalid_deepeval_run:expected an object with a testCases array")
    raw_cases = [c for c in data["testCases"] if isinstance(c, dict)]
    raw_cases += [c for c in data.get("conversationalTestCases") or [] if isinstance(c, dict)]
    metric_names = sorted(
        {str(m.get("name")) for c in raw_cases for m in c.get("metricsData") or []
         if isinstance(m, dict)}
    )
    if metric is not None and metric not in metric_names:
        raise ValueError(f"unknown_metric:{metric} (run has: {metric_names})")

    cases: list[dict[str, Any]] = []
    identity: dict[str, Any] = {}
    for i, c in enumerate(raw_cases):
        case_id = str(c.get("name") or f"test_case_{c.get('order', i)}")
        metrics = [m for m in c.get("metricsData") or [] if isinstance(m, dict)]
        if metric is not None:
            metrics = [m for m in metrics if m.get("name") == metric]
        scores: dict[str, float] = {}
        failed_metrics: list[str] = []
        for m in metrics:
            name = str(m.get("name"))
            value = _finite(m.get("score"))
            if m.get("error") or value is None:
                failed_metrics.append(name)
                value = 0.0
            elif m.get("success") is not True:
                failed_metrics.append(name)
            scores[name] = value
        if metric is not None:
            passed = bool(metrics) and not failed_metrics
        else:
            passed = c.get("success") is True and not failed_metrics and bool(metrics)
        entry: dict[str, Any] = {
            "id": case_id,
            "score": min(scores.values()) if scores else 0.0,
            "passed": passed,
            "tags": [str(t) for t in c.get("tags") or []],
            "missing_prediction": False,
            "scores": scores,
        }
        if failed_metrics:
            entry["failed_metrics"] = failed_metrics
        cases.append(entry)
        identity[case_id] = {
            k: c.get(k)
            for k in ("input", "expectedOutput", "context", "scenario", "expectedOutcome")
            if k in c
        }

    return _build_report(
        source="deepeval",
        name=str(data.get("testFile") or "deepeval-test-run"),
        cases=cases,
        identity=identity,
        source_info={"tool": "deepeval", "test_passed": data.get("testPassed"),
                     "test_failed": data.get("testFailed")},
        scorers=[metric] if metric else metric_names,
    )


IMPORTERS: dict[str, Callable[..., EvalReport]] = {
    "promptfoo": import_promptfoo,
    "inspect": import_inspect,
    "deepeval": import_deepeval,
}
