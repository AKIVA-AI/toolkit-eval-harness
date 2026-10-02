"""Score a predictions file against an evaluation suite.

Scoring rules (fail closed):

- The suite's *required scorers* are: ``json`` when ``scoring.json_schema`` is set,
  plus every name in ``scoring.scorers`` (``exact`` and ``json`` are built in; any
  other name must be a registered plugin scorer). With neither, the default is
  ``["exact"]``.
- A case passes only if every required scorer returns 1.0. The case score is the
  lowest required-scorer score, so one permissive scorer cannot hide another's failure.
- A case with no prediction (its id is absent, or its line has no ``prediction``
  field) fails with score 0.0 and ``missing_prediction: true``.
- An unknown scorer name, a prediction line without an ``id``, or a duplicate
  prediction id is an input error (``ValueError``), not a silent skip.
- ``scoring.scorers`` entries are names or objects ``{"name": ..., "label": ..., <options>}``
  for the configurable built-in scorers in :mod:`.scorers`. Network scorers (``embedding``,
  ``llm_judge``) are refused unless ``allow_network_scorers=True``.
"""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Any

from .metrics import SuiteMetrics
from .plugins import ScorerFunc, get_scorer
from .report import EvalReport
from .scorers import BUILTIN_SCORERS as CONFIGURABLE_SCORERS
from .scorers import BoundScorer, describe_config
from .scoring import JSONSchema, exact_match_score, json_required_keys_score, parse_json_schema
from .suite import EvalSuite

logger = logging.getLogger(__name__)

BUILTIN_SCORERS = ("exact", "json")


def _read_predictions(path: Path) -> tuple[dict[str, Any], set[str]]:
    """Return ``(predictions, seen_ids)``.

    ``predictions`` holds only lines that carry a ``prediction`` field; ``seen_ids``
    holds every id in the file.
    """
    preds: dict[str, Any] = {}
    seen: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid_prediction_line:line {lineno}: {exc.msg}") from exc
        if not isinstance(obj, dict):
            raise ValueError(f"invalid_prediction_line:line {lineno}: expected a JSON object")
        if obj.get("id") is None:
            raise ValueError(f"invalid_prediction_line:line {lineno}: missing 'id'")
        pid = str(obj["id"])
        if pid in seen:
            raise ValueError(f"duplicate_prediction_id:{pid} (line {lineno})")
        seen.add(pid)
        if "prediction" in obj:
            preds[pid] = obj["prediction"]
    logger.debug("Loaded %d predictions (%d ids) from %s", len(preds), len(seen), path)
    return preds, seen


def resolve_scorer_specs(scoring: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """Return ``(label, name, options)`` for every scorer each case must pass, in order.

    A string entry is a scorer name with no options (its label is the name). An object entry
    needs ``name`` and may set ``label`` (default: the name) and scorer options. Labels must be
    unique, so the same scorer can run twice with different options under two labels.
    """
    specs: list[tuple[str, str, dict[str, Any]]] = []
    if "json_schema" in scoring:
        specs.append(("json", "json", {}))
    raw = scoring.get("scorers")
    if raw is not None:
        if not isinstance(raw, list):
            raise ValueError("invalid_scoring:'scorers' must be a list of scorer names")
        for item in raw:
            if isinstance(item, dict):
                if not item.get("name"):
                    raise ValueError("invalid_scoring:scorer objects need a 'name'")
                name = str(item["name"])
                label = str(item.get("label") or name)
                options = {k: v for k, v in item.items() if k not in ("name", "label")}
            else:
                name = label = str(item)
                options = {}
            if any(label == existing for existing, _, _ in specs):
                if not options and name == label:
                    continue  # repeated plain name: keep the first, as before 1.0
                raise ValueError(f"invalid_scoring:duplicate scorer label {label!r}")
            specs.append((label, name, options))
    return specs or [("exact", "exact", {})]


def resolve_scorer_names(scoring: dict[str, Any]) -> list[str]:
    """Return the ordered labels of the scorers every case must pass."""
    return [label for label, _, _ in resolve_scorer_specs(scoring)]


def _build_configurable(
    name: str, options: dict[str, Any], *, allow_network_scorers: bool
) -> BoundScorer:
    spec = CONFIGURABLE_SCORERS[name]
    unknown = sorted(set(options) - set(spec.options))
    if unknown:
        raise ValueError(
            f"invalid_scorer_option:{name} does not accept {unknown}; "
            f"allowed: {list(spec.options)}"
        )
    if spec.network and not allow_network_scorers:
        raise ValueError(
            f"network_scorer_disabled:{name} calls a model over the network and is off by "
            "default; pass --allow-network-scorers (run_suite(allow_network_scorers=True))"
        )
    return spec.build(options)


def _normalise_plugin_score(value: Any) -> float | None:
    """Return *value* as a float in [0, 1], or None if it is not a valid score."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    score = float(value)
    if math.isnan(score) or score < 0.0 or score > 1.0:
        return None
    return score


def run_suite(
    *, suite: EvalSuite, predictions_path: Path, allow_network_scorers: bool = False
) -> EvalReport:
    logger.info(
        "Suite execution started: name=%s, cases=%d",
        suite.name,
        len(suite.cases),
    )
    suite_start = time.monotonic()

    predictions, seen_ids = _read_predictions(predictions_path)

    specs = resolve_scorer_specs(suite.scoring)
    scorer_names = [label for label, _, _ in specs]
    schema: JSONSchema | None = None
    if any(name == "json" for _, name, _ in specs):
        schema = parse_json_schema(dict(suite.scoring.get("json_schema") or {}))
    use_exact = any(name == "exact" for _, name, _ in specs)
    configured: list[tuple[str, BoundScorer]] = []
    scorer_config: dict[str, dict[str, Any]] = {}
    plugin_scorers: list[tuple[str, ScorerFunc, dict[str, Any]]] = []
    for label, name, options in specs:
        if name in BUILTIN_SCORERS:
            if options:
                raise ValueError(f"invalid_scorer_option:{name} takes no options")
            continue
        if name in CONFIGURABLE_SCORERS:
            bound = _build_configurable(
                name, options, allow_network_scorers=allow_network_scorers
            )
            configured.append((label, bound))
            scorer_config[label] = describe_config(name, options)
            continue
        try:
            plugin_scorers.append((label, get_scorer(name), options))
        except KeyError as exc:
            raise ValueError(f"unknown_scorer:{name}") from exc
    logger.debug("Required scorers: %s", scorer_names)

    case_ids = {case.id for case in suite.cases}
    unknown_predictions = len(seen_ids - case_ids)
    if unknown_predictions:
        logger.warning("%d prediction id(s) do not match any suite case", unknown_predictions)

    case_results: list[dict[str, Any]] = []
    metrics = SuiteMetrics()
    missing = 0

    for case in suite.cases:
        case_start = time.monotonic()
        result: dict[str, Any] = {"id": case.id, "tags": list(case.tags)}
        exact_meta: dict[str, Any] = {"enabled": False}
        json_meta: dict[str, Any] = {"enabled": False}

        if case.id not in predictions:
            missing += 1
            case_score = 0.0
            passed = False
            result["missing_prediction"] = True
            logger.debug("Case %s: no prediction", case.id)
        else:
            result["missing_prediction"] = False
            predicted = predictions[case.id]
            scores: list[float] = []

            if use_exact:
                s, meta = exact_match_score(expected=case.expected, predicted=predicted)
                exact_meta = {"enabled": True, **meta}
                scores.append(s)
            if schema is not None:
                s, meta = json_required_keys_score(
                    schema=schema, predicted=predicted, expected=case.expected
                )
                json_meta = {"enabled": True, "score": s, **meta}
                scores.append(s)

            builtin_results: dict[str, dict[str, Any]] = {}
            for scorer_label, bound_scorer in configured:
                try:
                    b_score, b_meta = bound_scorer(case.expected, predicted, case.input)
                except Exception as exc:  # noqa: BLE001 - a failing scorer fails the case
                    logger.warning(
                        "Scorer '%s' failed on case %s: %s", scorer_label, case.id, exc
                    )
                    builtin_results[scorer_label] = {
                        "score": 0.0,
                        "error": True,
                        "message": str(exc),
                    }
                    scores.append(0.0)
                    continue
                builtin_results[scorer_label] = {**b_meta, "score": b_score}
                scores.append(b_score)
            if builtin_results:
                result["scores"] = builtin_results

            plugin_results: dict[str, dict[str, Any]] = {}
            for scorer_name, scorer_func, p_options in plugin_scorers:
                try:
                    raw_score, p_meta = scorer_func(
                        expected=case.expected, predicted=predicted, **p_options
                    )
                except Exception:  # noqa: BLE001 - a crashing scorer fails the case
                    logger.warning(
                        "Plugin scorer '%s' failed on case %s", scorer_name, case.id,
                        exc_info=True,
                    )
                    plugin_results[scorer_name] = {"score": 0.0, "error": True}
                    scores.append(0.0)
                    continue
                p_score = _normalise_plugin_score(raw_score)
                if p_score is None:
                    logger.warning(
                        "Plugin scorer '%s' returned an invalid score %r on case %s",
                        scorer_name, raw_score, case.id,
                    )
                    plugin_results[scorer_name] = {"score": 0.0, "error": True}
                    scores.append(0.0)
                    continue
                plugin_results[scorer_name] = {**dict(p_meta or {}), "score": p_score}
                scores.append(p_score)
            if plugin_results:
                result["plugins"] = plugin_results

            case_score = min(scores)
            passed = all(s >= 1.0 for s in scores)

        result.update(
            {"score": case_score, "passed": passed, "exact": exact_meta, "json": json_meta}
        )
        case_results.append(result)
        case_elapsed = time.monotonic() - case_start
        # Every scorer returns a value in [0, 1], so ``passed`` == ``case_score >= 1.0``
        # and SuiteMetrics' pass/fail tally agrees with the per-case flag.
        metrics.record_case(score=case_score, elapsed=case_elapsed)

        logger.debug(
            "Case %s: score=%.2f, passed=%s, elapsed=%.4fs",
            case.id,
            case_score,
            passed,
            case_elapsed,
        )

    suite_elapsed = time.monotonic() - suite_start
    metrics.execution_time_seconds = suite_elapsed

    avg_score = metrics.average_score
    summary: dict[str, Any] = {
        "cases": metrics.total_cases,
        "score": avg_score,
        "passed": metrics.passed,
        "failed": metrics.failed,
        "missing_predictions": missing,
        "unknown_predictions": unknown_predictions,
        "scorers": scorer_names,
    }
    if scorer_config:
        summary["scorer_config"] = scorer_config

    logger.info(
        "Suite execution finished: name=%s, total=%d, passed=%d, failed=%d, "
        "missing=%d, avg_score=%.4f, elapsed=%.3fs",
        suite.name,
        metrics.total_cases,
        metrics.passed,
        metrics.failed,
        missing,
        avg_score,
        suite_elapsed,
    )

    return EvalReport(suite=suite.to_dict(), summary=summary, cases=case_results)
