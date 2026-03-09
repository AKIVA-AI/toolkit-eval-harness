"""Output formatters for CLI results.

Supports three output formats:
- **json** (default): Pretty-printed JSON.
- **table**: Human-readable ASCII table.
- **csv**: Comma-separated values suitable for spreadsheet import.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any


def format_json(data: dict[str, Any]) -> str:
    """Format data as pretty-printed JSON."""
    return json.dumps(data, indent=2, sort_keys=True)


def format_table(data: dict[str, Any]) -> str:
    """Format evaluation result data as a human-readable ASCII table.

    Handles two shapes:
    - Eval report (has ``summary`` and ``cases`` keys)
    - Generic dict (rendered as key-value pairs)
    """
    if "cases" in data and "summary" in data:
        return _format_report_table(data)
    return _format_dict_table(data)


def _format_report_table(data: dict[str, Any]) -> str:
    """Format an eval report as a table."""
    lines: list[str] = []

    # Suite header
    suite = data.get("suite", {})
    if suite.get("name"):
        lines.append(f"Suite: {suite['name']}")
    if suite.get("description"):
        lines.append(f"  {suite['description']}")
    lines.append("")

    # Summary
    summary = data.get("summary", {})
    lines.append("Summary")
    lines.append("-" * 40)
    for key in sorted(summary):
        val = summary[key]
        if isinstance(val, float):
            val = f"{val:.4f}"
        lines.append(f"  {key:<30s} {val}")
    lines.append("")

    # Cases table
    cases = data.get("cases", [])
    if cases:
        # Columns: ID, Score, Tags
        id_width = max(len("ID"), max((len(str(c.get("id", ""))) for c in cases), default=2))
        lines.append(f"{'ID':<{id_width}s}  {'Score':>8s}  Tags")
        lines.append(f"{'-' * id_width}  {'-' * 8}  {'-' * 20}")
        for c in cases:
            cid = str(c.get("id", ""))
            score = c.get("score", 0.0)
            tags = ", ".join(c.get("tags", []))
            lines.append(f"{cid:<{id_width}s}  {score:>8.4f}  {tags}")

    # Metadata
    metadata = data.get("metadata", {})
    if metadata:
        lines.append("")
        lines.append("Metadata")
        lines.append("-" * 40)
        for key in sorted(metadata):
            lines.append(f"  {key:<30s} {metadata[key]}")

    return "\n".join(lines)


def _format_dict_table(data: dict[str, Any]) -> str:
    """Format a generic dict as a key-value table."""
    lines: list[str] = []
    max_key = max((len(str(k)) for k in data), default=10)
    for key in sorted(data):
        val = data[key]
        if isinstance(val, (dict, list)):
            val = json.dumps(val, sort_keys=True)
        lines.append(f"{str(key):<{max_key}s}  {val}")
    return "\n".join(lines)


def format_csv(data: dict[str, Any]) -> str:
    """Format evaluation result data as CSV.

    For eval reports, outputs one row per case with columns:
    id, score, tags, exact_match, json_valid.

    For generic dicts, outputs key,value rows.
    """
    buf = io.StringIO()
    writer = csv.writer(buf)

    if "cases" in data and "summary" in data:
        # Header
        writer.writerow(["id", "score", "tags", "exact_match", "json_valid"])
        for c in data.get("cases", []):
            exact = c.get("exact", {})
            json_meta = c.get("json", {})
            writer.writerow(
                [
                    c.get("id", ""),
                    c.get("score", 0.0),
                    ";".join(c.get("tags", [])),
                    exact.get("match", ""),
                    json_meta.get("json_valid", ""),
                ]
            )
    else:
        writer.writerow(["key", "value"])
        for key in sorted(data):
            val = data[key]
            if isinstance(val, (dict, list)):
                val = json.dumps(val, sort_keys=True)
            writer.writerow([key, val])

    return buf.getvalue().rstrip("\n")


FORMATTERS: dict[str, Any] = {
    "json": format_json,
    "table": format_table,
    "csv": format_csv,
}


def get_formatter(name: str) -> Any:
    """Return the formatter function for the given format name.

    Args:
        name: One of ``"json"``, ``"table"``, ``"csv"``.

    Raises:
        ValueError: If *name* is not a recognised format.
    """
    if name not in FORMATTERS:
        available = ", ".join(sorted(FORMATTERS))
        raise ValueError(f"Unknown output format '{name}'. Available formats: {available}.")
    return FORMATTERS[name]
