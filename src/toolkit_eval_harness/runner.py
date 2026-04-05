from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from .metrics import SuiteMetrics
from .plugins import get_scorer
from .report import EvalReport
from .scoring import JSONSchema, exact_match_score, json_required_keys_score, parse_json_schema
from .suite import EvalSuite

logger = logging.getLogger(__name__)


def _read_predictions(path: Path) -> dict[str, Any]:
    preds: dict[str, Any] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        preds[str(obj["id"])] = obj.get("prediction")
    logger.debug("Loaded %d predictions from %s", len(preds), path)
    return preds


def _resolve_plugin_scorers(scoring: dict[str, Any]) -> list[str]:
    """Return list of plugin scorer names declared in suite.scoring['scorers']."""
    raw = scoring.get("scorers")
    if isinstance(raw, list):
        return [str(s) for s in raw]
    return []


def run_suite(*, suite: EvalSuite, predictions_path: Path) -> EvalReport:
    logger.info(
        "Suite execution started: name=%s, cases=%d",
        suite.name,
        len(suite.cases),
    )
    suite_start = time.monotonic()

    predictions = _read_predictions(predictions_path)

    schema: JSONSchema | None = None
    if "json_schema" in suite.scoring:
        schema = parse_json_schema(dict(suite.scoring.get("json_schema") or {}))
        logger.debug("JSON schema scoring enabled with keys: %s", schema.required_keys)

    plugin_scorer_names = _resolve_plugin_scorers(suite.scoring)
    plugin_scorers: list[tuple[str, Any]] = []
    for name in plugin_scorer_names:
        try:
            plugin_scorers.append((name, get_scorer(name)))
            logger.debug("Plugin scorer loaded: %s", name)
        except KeyError:
            logger.warning("Plugin scorer '%s' not found in registry, skipping", name)

    case_results: list[dict[str, Any]] = []
    metrics = SuiteMetrics()

    for case in suite.cases:
        case_start = time.monotonic()
        predicted = predictions.get(case.id)
        exact_score, exact_meta = exact_match_score(expected=case.expected, predicted=predicted)
        json_score = 0.0
        json_meta: dict[str, Any] = {"enabled": False}
        if schema is not None:
            json_score, json_meta = json_required_keys_score(schema=schema, predicted=predicted)
            json_meta = {"enabled": True, **json_meta}

        # Run plugin scorers and collect results
        plugin_results: dict[str, dict[str, Any]] = {}
        plugin_best_score = 0.0
        for scorer_name, scorer_func in plugin_scorers:
            try:
                p_score, p_meta = scorer_func(
                    expected=case.expected, predicted=predicted
                )
                plugin_results[scorer_name] = {"score": p_score, **p_meta}
                plugin_best_score = max(plugin_best_score, p_score)
            except Exception:  # noqa: BLE001
                logger.warning(
                    "Plugin scorer '%s' failed on case %s", scorer_name, case.id,
                    exc_info=True,
                )
                plugin_results[scorer_name] = {"score": 0.0, "error": True}

        case_score = max(exact_score, json_score, plugin_best_score)
        case_elapsed = time.monotonic() - case_start

        result: dict[str, Any] = {
            "id": case.id,
            "tags": list(case.tags),
            "score": case_score,
            "exact": exact_meta,
            "json": json_meta,
        }
        if plugin_results:
            result["plugins"] = plugin_results

        case_results.append(result)

        metrics.record_case(score=case_score, elapsed=case_elapsed)

        logger.debug(
            "Case %s: score=%.2f, elapsed=%.4fs",
            case.id,
            case_score,
            case_elapsed,
        )

    suite_elapsed = time.monotonic() - suite_start
    metrics.execution_time_seconds = suite_elapsed

    avg_score = metrics.average_score
    summary = {"cases": metrics.total_cases, "score": avg_score}

    logger.info(
        "Suite execution finished: name=%s, total=%d, passed=%d, failed=%d, "
        "skipped=%d, avg_score=%.4f, elapsed=%.3fs",
        suite.name,
        metrics.total_cases,
        metrics.passed,
        metrics.failed,
        metrics.skipped,
        avg_score,
        suite_elapsed,
    )

    return EvalReport(suite=suite.to_dict(), summary=summary, cases=case_results)
