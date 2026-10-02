"""Markdown output used by the GitHub Action job summary and PR comment."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from toolkit_eval_harness.cli import main
from toolkit_eval_harness.compare import CompareBudget, compare_reports
from toolkit_eval_harness.formatters import format_markdown
from toolkit_eval_harness.report import EvalReport

FIX = Path(__file__).resolve().parent / "fixtures" / "importers" / "promptfoo"


def _report(scores: dict[str, float], sha: str = "a" * 64) -> EvalReport:
    cases = [{"id": k, "score": v, "passed": v >= 1.0, "tags": ["t"]} for k, v in scores.items()]
    return EvalReport(suite={"name": "s", "sha256": sha},
                      summary={"score": sum(scores.values()) / len(scores)}, cases=cases)


def test_compare_markdown_shows_verdict_interval_and_flips() -> None:
    base = _report({"a": 1.0, "b": 1.0, "c": 0.0})
    cand = _report({"a": 1.0, "b": 0.0, "c": 1.0})
    res = compare_reports(baseline=base, candidate=cand, budget=CompareBudget(iterations=500))
    md = format_markdown(res)
    assert md.startswith("### :x: Eval gate failed (`score_regression`)")
    assert "| 95% CI of delta | [" in md
    assert "| Regression (upper bound) |" in md
    assert "**New failures:** `b`" in md and "**Fixes:** `c`" in md
    assert "<summary>Per tag</summary>" in md and "| `t` | 3 |" in md


def test_compare_markdown_pass_and_mismatch() -> None:
    base = _report({"a": 1.0})
    ok = format_markdown(compare_reports(baseline=base, candidate=base, budget=CompareBudget()))
    assert ok.startswith("### :white_check_mark: Eval gate passed")
    other = _report({"a": 1.0}, sha="b" * 64)
    bad = format_markdown(compare_reports(baseline=base, candidate=other, budget=CompareBudget()))
    assert "different suites" in bad and "b" * 64 in bad


def test_mean_method_markdown_has_no_interval() -> None:
    base = EvalReport(suite={}, summary={"score": 1.0}, cases=[])
    cand = EvalReport(suite={}, summary={"score": 0.5}, cases=[])
    md = format_markdown(compare_reports(baseline=base, candidate=cand, budget=CompareBudget()))
    assert "| Method | mean |" in md and "CI of delta" not in md
    assert "| Regression | 50.00% |" in md


def test_report_and_generic_markdown() -> None:
    md = format_markdown(_report({"a": 1.0, "b": 0.0}).to_dict())
    assert md.startswith("### :x: Eval run: `s`") and "**Failed cases:** `b`" in md
    assert format_markdown({"ok": True}).splitlines()[2] == "| ok | True |"


def test_cli_compare_markdown_output(tmp_path: Path) -> None:
    base, cand = tmp_path / "b.json", tmp_path / "c.json"
    main(["import", "promptfoo", str(FIX / "baseline.json"), "--out", str(base)])
    main(["import", "promptfoo", str(FIX / "candidate.json"), "--out", str(cand)])
    summary = tmp_path / "summary.md"
    rc = main(["--format", "markdown", "--output", str(summary), "compare", "--baseline",
               str(base), "--candidate", str(cand), "--max-new-failures", "0",
               "--max-score-regression-pct", "100"])
    assert rc == 1
    text = summary.read_text(encoding="utf-8")
    assert "Eval gate failed (`new_failures`)" in text
    assert "| New failures | 1 (max 0) |" in text
    assert "`two plus two`" in text


@pytest.mark.parametrize("fmt", ["json", "table", "csv", "markdown"])
def test_all_formats_are_accepted(tmp_path: Path, fmt: str) -> None:
    out = tmp_path / "o.txt"
    report = tmp_path / "r.json"
    report.write_text(json.dumps({"suite": {}, "summary": {}, "cases": []}), encoding="utf-8")
    assert main(["--format", fmt, "--output", str(out), "validate-report", "--report",
                 str(report)]) == 0
    assert out.read_text(encoding="utf-8")
