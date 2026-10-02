from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .envelope import KIND_IMPORT, KIND_RUN, STATEMENT_TYPE


@dataclass(frozen=True)
class EvalReport:
    suite: dict[str, Any]
    summary: dict[str, Any]
    cases: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {"suite": self.suite, "summary": self.summary, "cases": self.cases}

    @staticmethod
    def from_dict(obj: dict[str, Any]) -> EvalReport:
        """Build a report from a legacy report dict or an ``eval.run``/``eval.import`` envelope.

        Raises ``ValueError`` for an envelope of another kind (for example a compare report).
        """
        if isinstance(obj, dict) and obj.get("_type") == STATEMENT_TYPE:
            pred = obj.get("predicate") or {}
            if pred.get("kind") not in (KIND_RUN, KIND_IMPORT):
                raise ValueError(
                    f"not_a_run_report:envelope kind is {pred.get('kind')!r}, expected "
                    f"{KIND_RUN!r} or {KIND_IMPORT!r}"
                )
            details = pred.get("details") or {}
            return EvalReport(
                suite=dict(details.get("suite") or {}),
                summary=dict(pred.get("summary") or {}),
                cases=list(details.get("cases") or []),
            )
        return EvalReport(
            suite=dict(obj.get("suite") or {}),
            summary=dict(obj.get("summary") or {}),
            cases=list(obj.get("cases") or []),
        )


def write_report_json(report: EvalReport, path: Path) -> None:
    path.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
