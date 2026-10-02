from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvalCase:
    id: str
    input: Any
    expected: Any
    tags: list[str]


@dataclass(frozen=True)
class EvalSuite:
    schema_version: int
    name: str
    description: str
    created_at: str
    scoring: dict[str, Any]
    cases: list[EvalCase]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "scoring": dict(self.scoring),
            "cases_count": len(self.cases),
            "sha256": self.content_digest(),
        }

    def content_digest(self) -> str:
        """SHA-256 identifying the suite's content, independent of how it is packaged.

        It is the SHA-256 of the canonical JSON (sorted keys, compact, UTF-8) of the suite
        metadata (``schema_version``, ``name``, ``description``, ``created_at``, ``scoring``)
        and every case (``id``, ``input``, ``expected``, ``tags``) in file order. A suite
        directory and a pack built from it have the same digest. ``compare`` uses it to
        refuse comparing reports produced from different suites.
        """
        body = {
            "schema_version": self.schema_version,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "scoring": self.scoring,
            "cases": [
                {"id": c.id, "input": c.input, "expected": c.expected, "tags": list(c.tags)}
                for c in self.cases
            ],
        }
        text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_suite(*, suite_json: str, cases_jsonl: str) -> EvalSuite:
    """Build an :class:`EvalSuite` from the text of ``suite.json`` and ``cases.jsonl``.

    Raises ``ValueError`` for malformed input: a non-object ``suite.json``, a case line
    that is not a JSON object or has no ``id``, or two cases with the same id.
    """
    meta = json.loads(suite_json)
    if not isinstance(meta, dict):
        raise ValueError("invalid_suite:suite.json must contain a JSON object")
    schema_version = int(meta.get("schema_version", 1))
    name = str(meta.get("name", "unnamed"))
    description = str(meta.get("description", ""))
    created_at = str(meta.get("created_at", ""))
    scoring = dict(meta.get("scoring") or {})

    cases: list[EvalCase] = []
    seen: set[str] = set()
    for lineno, line in enumerate(cases_jsonl.splitlines(), start=1):
        if not line.strip():
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict) or obj.get("id") is None:
            raise ValueError(f"invalid_case:cases.jsonl line {lineno} needs an object with 'id'")
        case_id = str(obj["id"])
        if case_id in seen:
            raise ValueError(f"duplicate_case_id:{case_id} (cases.jsonl line {lineno})")
        seen.add(case_id)
        cases.append(
            EvalCase(
                id=case_id,
                input=obj.get("input"),
                expected=obj.get("expected"),
                tags=[str(x) for x in obj.get("tags", [])],
            )
        )
    return EvalSuite(
        schema_version=schema_version,
        name=name,
        description=description,
        created_at=created_at,
        scoring=scoring,
        cases=cases,
    )


def read_suite_dir(suite_dir: Path) -> EvalSuite:
    return parse_suite(
        suite_json=(suite_dir / "suite.json").read_text(encoding="utf-8"),
        cases_jsonl=(suite_dir / "cases.jsonl").read_text(encoding="utf-8"),
    )
