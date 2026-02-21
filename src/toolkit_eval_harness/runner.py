from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .report import EvalReport
from .scoring import JSONSchema, exact_match_score, json_required_keys_score, parse_json_schema
from .suite import EvalSuite


def _read_predictions(path: Path) -> dict[str, Any]:
    preds: dict[str, Any] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        preds[str(obj["id"])] = obj.get("prediction")
    return preds


def run_suite(*, suite: EvalSuite, predictions_path: Path) -> EvalReport:
    predictions = _read_predictions(predictions_path)

    schema: JSONSchema | None = None
    if "json_schema" in suite.scoring:
        schema = parse_json_schema(dict(suite.scoring.get("json_schema") or {}))

    case_results: list[dict[str, Any]] = []
    total = 0
    score_sum = 0.0

    for case in suite.cases:
        predicted = predictions.get(case.id)
        exact_score, exact_meta = exact_match_score(expected=case.expected, predicted=predicted)
        json_score = 0.0
        json_meta: dict[str, Any] = {"enabled": False}
        if schema is not None:
            json_score, json_meta = json_required_keys_score(schema=schema, predicted=predicted)
            json_meta = {"enabled": True, **json_meta}
        case_score = max(exact_score, json_score)

        case_results.append(
            {
                "id": case.id,
                "tags": list(case.tags),
                "score": case_score,
                "exact": exact_meta,
                "json": json_meta,
            }
        )

        total += 1
        score_sum += case_score

    avg_score = (score_sum / total) if total else 0.0
    summary = {"cases": total, "score": avg_score}
    return EvalReport(suite=suite.to_dict(), summary=summary, cases=case_results)
