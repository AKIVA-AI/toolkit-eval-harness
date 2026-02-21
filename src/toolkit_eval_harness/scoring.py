from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class JSONSchema:
    required_keys: list[str]
    optional_keys: list[str]
    allow_extra_keys: bool = True


def parse_json_schema(obj: dict[str, Any]) -> JSONSchema:
    return JSONSchema(
        required_keys=[str(x) for x in obj.get("required_keys", [])],
        optional_keys=[str(x) for x in obj.get("optional_keys", [])],
        allow_extra_keys=bool(obj.get("allow_extra_keys", True)),
    )


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
        return 1.0, {"match": True}
    return 0.0, {"match": False}


def json_required_keys_score(*, schema: JSONSchema, predicted: Any) -> tuple[float, dict[str, Any]]:
    ok, obj = _to_json_obj(predicted)
    if not ok:
        return 0.0, {"json_valid": False, "reasons": ["invalid_json"]}
    valid, reasons = validate_json(obj, schema)
    if not schema.required_keys:
        return 1.0, {"json_valid": valid, "reasons": reasons}
    present = sum(1 for k in schema.required_keys if isinstance(obj, dict) and k in obj)
    return present / len(schema.required_keys), {"json_valid": valid, "reasons": reasons}
