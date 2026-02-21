from __future__ import annotations

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
        }


def read_suite_dir(suite_dir: Path) -> EvalSuite:
    meta = json.loads((suite_dir / "suite.json").read_text(encoding="utf-8"))
    schema_version = int(meta.get("schema_version", 1))
    name = str(meta.get("name", "unnamed"))
    description = str(meta.get("description", ""))
    created_at = str(meta.get("created_at", ""))
    scoring = dict(meta.get("scoring") or {})

    cases: list[EvalCase] = []
    for line in (suite_dir / "cases.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        cases.append(
            EvalCase(
                id=str(obj["id"]),
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
