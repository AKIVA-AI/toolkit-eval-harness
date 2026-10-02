"""Output formatters for CLI results.

Supports four output formats:
- **json** (default): Pretty-printed JSON.
- **table**: Human-readable ASCII table.
- **csv**: Comma-separated values suitable for spreadsheet import.
- **markdown**: GitHub-flavoured Markdown (compare results, reports) for job summaries.
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


def _num(value: Any, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _pct(value: Any) -> str:
    return "n/a" if value is None else f"{float(value):.2f}%"


def _id_list(ids: list[Any], limit: int = 20) -> str:
    shown = ", ".join(f"`{i}`" for i in ids[:limit])
    return shown + (f" and {len(ids) - limit} more" if len(ids) > limit else "")


def _format_compare_markdown(data: dict[str, Any]) -> str:
    reason = data.get("reason")
    if data.get("passed"):
        head = "### :white_check_mark: Eval gate passed"
    elif reason == "suite_mismatch":
        head = "### :x: Eval gate error: reports come from different suites"
    else:
        head = f"### :x: Eval gate failed (`{reason}`)"
    lines = [head, ""]
    lines += ["| Metric | Value |", "|---|---|"]
    rows: list[tuple[str, str]] = [
        ("Method", str(data.get("method"))),
        ("Suite check", str(data.get("suite_check", "n/a"))),
        ("Paired cases", _num(data.get("paired_cases"))),
        ("Baseline score", _num(data.get("baseline_score"))),
        ("Candidate score", _num(data.get("candidate_score"))),
    ]
    if data.get("method") == "bootstrap" and "ci_low" in data:
        conf = float(data.get("confidence") or 0.95) * 100
        rows += [
            ("Mean delta", _num(data.get("mean_delta"))),
            (
                f"{conf:g}% CI of delta",
                f"[{_num(data.get('ci_low'))}, {_num(data.get('ci_high'))}]",
            ),
            ("Regression (point)", _pct(data.get("score_regression_pct"))),
            ("Regression (upper bound)", _pct(data.get("regression_pct_upper"))),
        ]
    else:
        rows.append(("Regression", _pct(data.get("score_regression_pct"))))
    rows.append(("Budget", _pct(data.get("max_score_regression_pct"))))
    if "new_failure_count" in data:
        budget = data.get("max_new_failures")
        suffix = "" if budget is None else f" (max {budget})"
        rows += [
            ("New failures", f"{data['new_failure_count']}{suffix}"),
            ("Fixes", _num(data.get("fix_count"))),
        ]
    lines += [f"| {k} | {v} |" for k, v in rows]
    if data.get("new_failures"):
        lines += ["", f"**New failures:** {_id_list(list(data['new_failures']))}"]
    if data.get("fixes"):
        lines += ["", f"**Fixes:** {_id_list(list(data['fixes']))}"]
    per_tag = data.get("per_tag") or {}
    if per_tag:
        lines += ["", "<details><summary>Per tag</summary>", "",
                  "| Tag | Cases | Baseline | Candidate | Delta | New failures | Fixes |",
                  "|---|---|---|---|---|---|---|"]
        for tag, t in per_tag.items():
            lines.append(
                f"| `{tag}` | {t['cases']} | {_num(t['baseline_score'])} | "
                f"{_num(t['candidate_score'])} | {_num(t['delta'])} | {t['new_failures']} | "
                f"{t['fixes']} |"
            )
        lines += ["", "</details>"]
    if reason == "suite_mismatch":
        lines += ["", f"Baseline suite `{data.get('baseline_suite_sha256')}`, candidate suite "
                      f"`{data.get('candidate_suite_sha256')}`."]
    return "\n".join(lines) + "\n"


def _format_report_markdown(data: dict[str, Any]) -> str:
    summary = data.get("summary", {})
    name = data.get("suite", {}).get("name", "suite")
    failed = [c for c in data.get("cases", []) if not c.get("passed")]
    icon = ":white_check_mark:" if not failed and summary.get("cases") else ":x:"
    lines = [f"### {icon} Eval run: `{name}`", "", "| Metric | Value |", "|---|---|"]
    for key in ("cases", "passed", "failed", "score", "missing_predictions"):
        if key in summary:
            lines.append(f"| {key} | {_num(summary[key])} |")
    if failed:
        lines += ["", f"**Failed cases:** {_id_list([c.get('id') for c in failed])}"]
    return "\n".join(lines) + "\n"


def format_markdown(data: dict[str, Any]) -> str:
    """GitHub-flavoured Markdown, e.g. for ``$GITHUB_STEP_SUMMARY`` or a PR comment."""
    if "passed" in data and "reason" in data and "baseline_score" in data:
        return _format_compare_markdown(data)
    if "cases" in data and "summary" in data:
        return _format_report_markdown(data)
    lines = ["| Key | Value |", "|---|---|"]
    for key in sorted(data):
        val = data[key]
        if isinstance(val, (dict, list)):
            val = json.dumps(val, sort_keys=True)
        lines.append(f"| {key} | {val} |")
    return "\n".join(lines) + "\n"


FORMATTERS: dict[str, Any] = {
    "json": format_json,
    "table": format_table,
    "csv": format_csv,
    "markdown": format_markdown,
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
