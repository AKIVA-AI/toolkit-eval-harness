"""Tests for output formatters (json, table, csv)."""

from __future__ import annotations

import csv
import io
import json

from toolkit_eval_harness.formatters import format_csv, format_json, format_table, get_formatter

import pytest


# ---------------------------------------------------------------------------
# format_json
# ---------------------------------------------------------------------------


def test_format_json_roundtrip() -> None:
    data = {"key": "value", "number": 42}
    output = format_json(data)
    assert json.loads(output) == data


def test_format_json_sorted_keys() -> None:
    data = {"z": 1, "a": 2}
    output = format_json(data)
    assert output.index('"a"') < output.index('"z"')


# ---------------------------------------------------------------------------
# format_table — eval report shape
# ---------------------------------------------------------------------------


def test_format_table_report() -> None:
    data = {
        "suite": {"name": "demo", "description": "A demo suite"},
        "summary": {"cases": 2, "score": 0.75},
        "cases": [
            {"id": "c1", "score": 1.0, "tags": ["fast"]},
            {"id": "c2", "score": 0.5, "tags": ["slow", "edge"]},
        ],
        "metadata": {"tool_version": "0.1.0"},
    }
    output = format_table(data)
    assert "Suite: demo" in output
    assert "A demo suite" in output
    assert "c1" in output
    assert "c2" in output
    assert "1.0000" in output
    assert "0.5000" in output
    assert "fast" in output
    assert "slow, edge" in output
    assert "tool_version" in output


def test_format_table_generic_dict() -> None:
    data = {"alpha": 1, "beta": "two"}
    output = format_table(data)
    assert "alpha" in output
    assert "beta" in output


def test_format_table_empty_cases() -> None:
    data = {"suite": {"name": "empty"}, "summary": {"cases": 0}, "cases": []}
    output = format_table(data)
    assert "Suite: empty" in output


# ---------------------------------------------------------------------------
# format_csv — eval report shape
# ---------------------------------------------------------------------------


def test_format_csv_report_header() -> None:
    data = {
        "suite": {},
        "summary": {"cases": 1, "score": 1.0},
        "cases": [
            {
                "id": "c1",
                "score": 1.0,
                "tags": ["tag1", "tag2"],
                "exact": {"match": True},
                "json": {"json_valid": True},
            }
        ],
    }
    output = format_csv(data)
    reader = csv.reader(io.StringIO(output))
    rows = list(reader)
    assert rows[0] == ["id", "score", "tags", "exact_match", "json_valid"]
    assert rows[1][0] == "c1"
    assert rows[1][2] == "tag1;tag2"


def test_format_csv_generic_dict() -> None:
    data = {"x": 1, "y": [1, 2]}
    output = format_csv(data)
    reader = csv.reader(io.StringIO(output))
    rows = list(reader)
    assert rows[0] == ["key", "value"]
    assert len(rows) == 3  # header + 2 data rows


# ---------------------------------------------------------------------------
# get_formatter
# ---------------------------------------------------------------------------


def test_get_formatter_valid() -> None:
    for name in ("json", "table", "csv"):
        f = get_formatter(name)
        assert callable(f)


def test_get_formatter_invalid() -> None:
    with pytest.raises(ValueError, match="Unknown output format"):
        get_formatter("xml")
