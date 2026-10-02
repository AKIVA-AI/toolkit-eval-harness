"""Report envelope v1: every machine-readable report is an in-toto Statement v1.

The format is specified in ``docs/report-envelope.md`` and ``schemas/report-envelope.v1.json``.
This module builds envelopes, writes them as canonical JSON, and checks their structure
without third-party dependencies.

Canonical JSON: UTF-8, keys sorted, no insignificant whitespace, one trailing newline, and
no NaN or infinity. The SHA-256 of the file is therefore stable for a given report.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .hashing import sha256_file

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
TOOL_NAME = "toolkit-eval-harness"
PREDICATE_TYPE = "https://github.com/AKIVA-AI/toolkit-eval-harness/report/v1"

KIND_RUN = "eval.run"
KIND_COMPARE = "eval.compare"
KIND_IMPORT = "eval.import"

VERDICTS = ("pass", "fail", "error")

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_KIND_RE = re.compile(r"^[a-z][a-z0-9_-]*\.[a-z][a-z0-9_.-]*$")
_CREATED_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+)?Z$")
_PREDICATE_TYPE_RE = re.compile(r"^https://github\.com/AKIVA-AI/[A-Za-z0-9._-]+/report/v1$")
_PREDICATE_KEYS = (
    "tool",
    "kind",
    "created_at",
    "verdict",
    "exit_code",
    "inputs",
    "summary",
    "details",
)


def canonical_json_bytes(obj: Any) -> bytes:
    """Serialize *obj* as canonical JSON (sorted keys, compact, UTF-8, trailing newline).

    Raises ``ValueError`` for NaN or infinite floats, which JSON cannot represent.
    """
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False)
    return (text + "\n").encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(obj: Any) -> str:
    """SHA-256 of the canonical JSON of *obj* (without the trailing newline)."""
    return sha256_bytes(canonical_json_bytes(obj)[:-1])


def resource(name: str, sha256: str) -> dict[str, Any]:
    """Return an in-toto resource descriptor ``{"name", "digest": {"sha256"}}``."""
    return {"name": name, "digest": {"sha256": sha256}}


def file_resource(path: Path, name: str | None = None) -> dict[str, Any]:
    """Resource descriptor for a file, named *name* or the path as given."""
    return resource(name if name is not None else str(path), sha256_file(path))


def utc_now_rfc3339() -> str:
    """Current UTC time as RFC 3339 with a ``Z`` suffix, to the second.

    Honours ``SOURCE_DATE_EPOCH`` (reproducible-builds convention) so reports can be made
    byte-for-byte reproducible.
    """
    epoch = os.environ.get("SOURCE_DATE_EPOCH", "").strip()
    moment = (
        datetime.fromtimestamp(int(epoch), tz=timezone.utc)
        if epoch.isdigit()
        else datetime.now(tz=timezone.utc)
    )
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def verdict_for_exit_code(exit_code: int) -> str:
    """Map a CLI exit code to a verdict: 0 pass, 1 fail, anything else error."""
    if exit_code == 0:
        return "pass"
    if exit_code == 1:
        return "fail"
    return "error"


def build_statement(
    *,
    kind: str,
    subject: list[dict[str, Any]],
    exit_code: int,
    inputs: list[dict[str, Any]],
    summary: dict[str, Any],
    details: dict[str, Any],
    tool_version: str,
    created_at: str | None = None,
) -> dict[str, Any]:
    """Assemble an envelope. The verdict is derived from *exit_code* so the two agree."""
    return {
        "_type": STATEMENT_TYPE,
        "subject": subject,
        "predicateType": PREDICATE_TYPE,
        "predicate": {
            "tool": {"name": TOOL_NAME, "version": tool_version},
            "kind": kind,
            "created_at": created_at or utc_now_rfc3339(),
            "verdict": verdict_for_exit_code(exit_code),
            "exit_code": int(exit_code),
            "inputs": inputs,
            "summary": summary,
            "details": details,
        },
    }


def write_envelope(path: Path, statement: dict[str, Any]) -> str:
    """Write *statement* as canonical JSON and return the file's SHA-256."""
    data = canonical_json_bytes(statement)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return sha256_bytes(data)


def is_envelope(obj: Any) -> bool:
    return isinstance(obj, dict) and obj.get("_type") == STATEMENT_TYPE


def _check_resources(value: Any, where: str, errors: list[str], *, non_empty: bool) -> None:
    if not isinstance(value, list):
        errors.append(f"{where} must be an array")
        return
    if non_empty and not value:
        errors.append(f"{where} must not be empty")
    for i, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{where}[{i}] must be an object")
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name:
            errors.append(f"{where}[{i}].name must be a non-empty string")
        digest = item.get("digest")
        if not isinstance(digest, dict):
            errors.append(f"{where}[{i}].digest must be an object")
            continue
        sha = digest.get("sha256")
        if not isinstance(sha, str) or not _SHA256_RE.match(sha):
            errors.append(f"{where}[{i}].digest.sha256 must be 64 lowercase hex characters")
        for algo, val in digest.items():
            if not isinstance(val, str):
                errors.append(f"{where}[{i}].digest.{algo} must be a string")


def validate_envelope(obj: Any) -> list[str]:
    """Return a list of problems with *obj* as a v1 envelope (empty when valid).

    Mirrors ``schemas/report-envelope.v1.json``; the test suite checks that the two agree.
    """
    errors: list[str] = []
    if not isinstance(obj, dict):
        return ["envelope must be a JSON object"]
    if obj.get("_type") != STATEMENT_TYPE:
        errors.append(f"_type must be {STATEMENT_TYPE}")
    _check_resources(obj.get("subject"), "subject", errors, non_empty=True)
    ptype = obj.get("predicateType")
    if not isinstance(ptype, str) or not _PREDICATE_TYPE_RE.match(ptype):
        errors.append("predicateType must be https://github.com/AKIVA-AI/<repo>/report/v1")
    pred = obj.get("predicate")
    if not isinstance(pred, dict):
        errors.append("predicate must be an object")
        return errors
    for key in _PREDICATE_KEYS:
        if key not in pred:
            errors.append(f"predicate.{key} is required")
    tool = pred.get("tool")
    if "tool" in pred:
        if not isinstance(tool, dict):
            errors.append("predicate.tool must be an object")
        else:
            for key in ("name", "version"):
                if not isinstance(tool.get(key), str) or not tool.get(key):
                    errors.append(f"predicate.tool.{key} must be a non-empty string")
    kind = pred.get("kind")
    if "kind" in pred and (not isinstance(kind, str) or not _KIND_RE.match(kind)):
        errors.append("predicate.kind must look like '<area>.<command>', e.g. eval.run")
    created = pred.get("created_at")
    if "created_at" in pred and (not isinstance(created, str) or not _CREATED_RE.match(created)):
        errors.append("predicate.created_at must be RFC 3339 UTC ending in 'Z'")
    else:
        try:
            if isinstance(created, str):
                datetime.strptime(created[:19], "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            errors.append("predicate.created_at is not a valid date-time")
    verdict = pred.get("verdict")
    if "verdict" in pred and verdict not in VERDICTS:
        errors.append("predicate.verdict must be pass, fail or error")
    code = pred.get("exit_code")
    if "exit_code" in pred:
        if isinstance(code, bool) or not isinstance(code, int) or code < 0:
            errors.append("predicate.exit_code must be a non-negative integer")
        elif verdict == "pass" and code != 0:
            errors.append("predicate.verdict 'pass' requires exit_code 0")
        elif verdict in ("fail", "error") and code == 0:
            errors.append(f"predicate.verdict '{verdict}' requires a non-zero exit_code")
    if "inputs" in pred:
        _check_resources(pred.get("inputs"), "predicate.inputs", errors, non_empty=False)
    for key in ("summary", "details"):
        if key in pred and not isinstance(pred.get(key), dict):
            errors.append(f"predicate.{key} must be an object")
    return errors
