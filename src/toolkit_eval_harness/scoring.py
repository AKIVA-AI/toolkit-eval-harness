from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class JSONSchema:
    required_keys: list[str]
    optional_keys: list[str]
    allow_extra_keys: bool = True


def parse_json_schema(obj: dict[str, Any]) -> JSONSchema:
    schema = JSONSchema(
        required_keys=[str(x) for x in obj.get("required_keys", [])],
        optional_keys=[str(x) for x in obj.get("optional_keys", [])],
        allow_extra_keys=bool(obj.get("allow_extra_keys", True)),
    )
    logger.debug(
        "Parsed JSON schema: required=%s, optional=%s, allow_extra=%s",
        schema.required_keys,
        schema.optional_keys,
        schema.allow_extra_keys,
    )
    return schema


def _to_json_obj(prediction: Any) -> tuple[bool, Any]:
    if isinstance(prediction, (dict, list)):
        return True, prediction
    if not isinstance(prediction, str):
        return False, None
    try:
        return True, json.loads(prediction)
    except Exception:  # noqa: BLE001
        return False, None


def validate_json(obj: Any, schema: JSONSchema) -> tuple[bool, list[str]]:
    if not isinstance(obj, dict):
        return False, ["not_object"]

    reasons: list[str] = []
    ok = True

    for k in schema.required_keys:
        if k not in obj:
            ok = False
            reasons.append(f"missing_key:{k}")

    if not schema.allow_extra_keys:
        allowed = set(schema.required_keys).union(schema.optional_keys)
        extras = [k for k in obj.keys() if k not in allowed]
        if extras:
            ok = False
            reasons.append("extra_keys:" + ",".join(sorted(extras)))

    return ok, reasons


def exact_match_score(*, expected: Any, predicted: Any) -> tuple[float, dict[str, Any]]:
    if expected == predicted:
        logger.debug("Exact match: predicted matches expected")
        return 1.0, {"match": True}
    logger.debug("Exact match failed: expected=%r, predicted=%r", expected, predicted)
    return 0.0, {"match": False}


def json_required_keys_score(*, schema: JSONSchema, predicted: Any) -> tuple[float, dict[str, Any]]:
    ok, obj = _to_json_obj(predicted)
    if not ok:
        logger.debug("JSON scoring: prediction is not valid JSON")
        return 0.0, {"json_valid": False, "reasons": ["invalid_json"]}
    valid, reasons = validate_json(obj, schema)
    if not schema.required_keys:
        return 1.0, {"json_valid": valid, "reasons": reasons}
    present = sum(1 for k in schema.required_keys if isinstance(obj, dict) and k in obj)
    score = present / len(schema.required_keys)
    logger.debug(
        "JSON keys scoring: %d/%d required keys present, score=%.2f",
        present,
        len(schema.required_keys),
        score,
    )
    return score, {"json_valid": valid, "reasons": reasons}
