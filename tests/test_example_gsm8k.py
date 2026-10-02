"""The README's 5-minute example must produce the numbers the README shows."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from toolkit_eval_harness.cli import main

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "gsm8k-20"


def test_gsm8k_example_end_to_end(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base, cand, cmp_out = tmp_path / "baseline.json", tmp_path / "candidate.json", tmp_path / "c"
    assert main(["run", "--suite", str(EXAMPLE), "--predictions",
                 str(EXAMPLE / "preds-baseline.jsonl"), "--out", str(base)]) == 1
    assert main(["run", "--suite", str(EXAMPLE), "--predictions",
                 str(EXAMPLE / "preds-candidate.jsonl"), "--out", str(cand)]) == 1
    b = json.loads(base.read_text(encoding="utf-8"))["predicate"]["summary"]
    c = json.loads(cand.read_text(encoding="utf-8"))["predicate"]["summary"]
    assert (b["cases"], b["passed"], c["passed"]) == (20, 17, 16)

    capsys.readouterr()
    rc = main(["compare", "--baseline", str(base), "--candidate", str(cand),
               "--out", str(cmp_out)])
    assert rc == 1
    s = json.loads(cmp_out.read_text(encoding="utf-8"))["predicate"]["summary"]
    assert s["suite_check"] == "match"
    assert (s["new_failure_count"], s["fix_count"]) == (2, 1)
    assert s["mean_delta"] == pytest.approx(-0.05)
    assert (s["ci_low"], s["ci_high"]) == (pytest.approx(-0.2), pytest.approx(0.1))
    assert s["regression_pct_upper"] == pytest.approx(23.53, abs=0.01)
    assert s["reason"] == "score_regression"
    # The mean-only gate would also fail here (5.88% > 2%); a 10% budget shows the difference.
    assert main(["compare", "--baseline", str(base), "--candidate", str(cand),
                 "--max-score-regression-pct", "10", "--method", "mean"]) == 0
    assert main(["compare", "--baseline", str(base), "--candidate", str(cand),
                 "--max-score-regression-pct", "10"]) == 1
