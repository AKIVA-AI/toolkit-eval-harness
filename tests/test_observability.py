"""Tests for observability hardening: structured logging, CLI flags, diagnostics, timing."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from toolkit_eval_harness.cli import EXIT_SUCCESS, EXIT_VALIDATION_FAILED, build_parser, main
from toolkit_eval_harness.logging_config import JSONFormatter, setup_logging


# ---------------------------------------------------------------------------
# Structured logging (JSON formatter)
# ---------------------------------------------------------------------------


class TestJSONFormatter:
    def test_basic_json_output(self) -> None:
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello %s",
            args=("world",),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert parsed["level"] == "INFO"
        assert parsed["message"] == "hello world"
        assert parsed["logger"] == "test"
        assert "timestamp" in parsed

    def test_json_with_exception(self) -> None:
        formatter = JSONFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="failed",
            args=(),
            exc_info=exc_info,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "exception" in parsed
        assert "boom" in parsed["exception"]


class TestSetupLogging:
    def test_text_format(self) -> None:
        setup_logging(level=logging.DEBUG, fmt="text")
        root = logging.getLogger()
        assert root.level == logging.DEBUG
        assert len(root.handlers) == 1
        assert not isinstance(root.handlers[0].formatter, JSONFormatter)

    def test_json_format(self) -> None:
        setup_logging(level=logging.INFO, fmt="json")
        root = logging.getLogger()
        assert isinstance(root.handlers[0].formatter, JSONFormatter)

    def test_idempotent_no_duplicates(self) -> None:
        setup_logging(level=logging.WARNING, fmt="text")
        setup_logging(level=logging.WARNING, fmt="text")
        root = logging.getLogger()
        assert len(root.handlers) == 1


# ---------------------------------------------------------------------------
# CLI flags: --verbose, --quiet, --log-format
# ---------------------------------------------------------------------------


class TestCLIFlags:
    def test_verbose_and_quiet_are_mutually_exclusive(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--verbose", "--quiet", "check-deps"])

    def test_verbose_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--verbose", "check-deps"])
        assert args.verbose is True
        assert args.quiet is False

    def test_quiet_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--quiet", "check-deps"])
        assert args.quiet is True
        assert args.verbose is False

    def test_log_format_choices(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--log-format", "json", "check-deps"])
        assert args.log_format == "json"

    def test_log_format_invalid_rejected(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--log-format", "xml", "check-deps"])


# ---------------------------------------------------------------------------
# check-deps subcommand
# ---------------------------------------------------------------------------


class TestCheckDeps:
    def test_check_deps_success(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main(["check-deps"])
        assert rc == EXIT_SUCCESS
        output = json.loads(capsys.readouterr().out)
        assert output["all_ok"] is True
        assert any(c["name"] == "python>=3.10" for c in output["checks"])

    def test_check_deps_includes_version(self, capsys: pytest.CaptureFixture[str]) -> None:
        rc = main(["check-deps"])
        assert rc == EXIT_SUCCESS
        output = json.loads(capsys.readouterr().out)
        assert output["tool"] == "toolkit-eval"
        assert "version" in output


# ---------------------------------------------------------------------------
# Timing/metrics in eval run output
# ---------------------------------------------------------------------------


class TestRunTimingMetrics:
    def test_run_includes_timing_and_counts(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # Create a minimal suite
        suite_dir = tmp_path / "suite"
        suite_dir.mkdir()
        (suite_dir / "suite.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "name": "timing-test",
                    "description": "test timing",
                    "created_at": "2025-01-01T00:00:00Z",
                    "scoring": {},
                }
            ),
            encoding="utf-8",
        )
        (suite_dir / "cases.jsonl").write_text(
            json.dumps({"id": "c1", "input": {"prompt": "x"}, "expected": "yes"})
            + "\n"
            + json.dumps({"id": "c2", "input": {"prompt": "y"}, "expected": "no"})
            + "\n",
            encoding="utf-8",
        )
        preds = tmp_path / "preds.jsonl"
        preds.write_text(
            json.dumps({"id": "c1", "prediction": "yes"})
            + "\n"
            + json.dumps({"id": "c2", "prediction": "wrong"})
            + "\n",
            encoding="utf-8",
        )

        rc = main(
            ["run", "--suite", str(suite_dir), "--predictions", str(preds)]
        )
        assert rc == EXIT_SUCCESS
        output = json.loads(capsys.readouterr().out)

        summary = output["summary"]
        assert "execution_time_seconds" in summary
        assert summary["execution_time_seconds"] >= 0
        assert summary["pass_count"] == 1
        assert summary["fail_count"] == 1
        assert summary["cases"] == 2

        # Metadata present
        assert "metadata" in output
        assert "tool_version" in output["metadata"]
        assert "python_version" in output["metadata"]
