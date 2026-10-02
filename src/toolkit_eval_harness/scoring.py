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


def json_required_keys_score(
    *, schema: JSONSchema, predicted: Any, expected: Any = None
) -> tuple[float, dict[str, Any]]:
    """Score a JSON prediction against *schema* and, where given, *expected* values.

    Each of these is one check; the score is the fraction of checks that pass:

    - every ``schema.required_keys`` entry must be present, and must equal
      ``expected[key]`` when *expected* is an object that has that key;
    - every other key of an *expected* object must be present with an equal value;
    - when ``allow_extra_keys`` is false, the absence of extra keys is one more check.

    A prediction that is not a JSON object scores 0.0. With no checks at all
    (no required keys, no expected object, extra keys allowed) any object scores 1.0.
    """
    ok, obj = _to_json_obj(predicted)
    if not ok:
        logger.debug("JSON scoring: prediction is not valid JSON")
        return 0.0, {"json_valid": False, "reasons": ["invalid_json"]}
    valid, reasons = validate_json(obj, schema)
    if not isinstance(obj, dict):
        return 0.0, {"json_valid": False, "reasons": reasons}

    expected_obj: dict[str, Any] = {}
    if expected is not None:
        exp_ok, exp = _to_json_obj(expected)
        if exp_ok and isinstance(exp, dict):
            expected_obj = exp

    keys = list(dict.fromkeys([*schema.required_keys, *expected_obj.keys()]))
    total = len(keys)
    passed = 0
    for k in keys:
        if k not in obj:
            if k not in schema.required_keys:
                reasons.append(f"missing_key:{k}")
            continue
        if k in expected_obj and obj[k] != expected_obj[k]:
            reasons.append(f"value_mismatch:{k}")
            continue
        passed += 1

    if not schema.allow_extra_keys:
        total += 1
        if not any(r.startswith("extra_keys:") for r in reasons):
            passed += 1

    score = (passed / total) if total else 1.0
    logger.debug("JSON scoring: %d/%d checks passed, score=%.2f", passed, total, score)
    return score, {"json_valid": valid, "reasons": reasons}
