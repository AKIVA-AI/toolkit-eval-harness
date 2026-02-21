from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvalReport:
    suite: dict[str, Any]
    summary: dict[str, Any]
    cases: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"suite": self.suite, "summary": self.summary, "cases": self.cases}

    @staticmethod
    def from_dict(obj: dict[str, Any]) -> EvalReport:
        return EvalReport(
            suite=dict(obj.get("suite") or {}),
            summary=dict(obj.get("summary") or {}),
            cases=list(obj.get("cases") or []),
        )


def write_report_json(report: EvalReport, path: Path) -> None:
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
