"""Write the two illustrative prediction files for the GSM8K-20 example.

These are NOT model outputs. They are written by this script so the example runs offline
and has a known answer: the "baseline" answers 17 of 20 problems correctly and the
"candidate" 16 of 20, fixing one baseline mistake and introducing two new ones.

    python examples/gsm8k-20/make_predictions.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE_WRONG = {"gsm8k-test-0004", "gsm8k-test-0011", "gsm8k-test-0017"}
CANDIDATE_WRONG = {"gsm8k-test-0004", "gsm8k-test-0011", "gsm8k-test-0006", "gsm8k-test-0013"}


def answer(case_id: str, expected: float, wrong: set[str]) -> str:
    value = expected + 1 if case_id in wrong else expected
    return f"Working through the problem step by step, the answer is {value}."


def main() -> None:
    cases = [json.loads(line) for line in (HERE / "cases.jsonl").read_text("utf-8").splitlines()]
    for name, wrong in (("preds-baseline.jsonl", BASELINE_WRONG),
                        ("preds-candidate.jsonl", CANDIDATE_WRONG)):
        lines = [
            json.dumps({"id": c["id"], "prediction": answer(c["id"], c["expected"], wrong)})
            for c in cases
        ]
        (HERE / name).write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
