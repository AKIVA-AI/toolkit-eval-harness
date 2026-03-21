"""Tests for observability hardening: structured logging, metrics, health checks, timing."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from toolkit_eval_harness.cli import EXIT_SUCCESS, build_parser, main
from toolkit_eval_harness.health import check_health
from toolkit_eval_harness.logging_config import JSONFormatter, setup_logging
from toolkit_eval_harness.metrics import MetricsCollector, SuiteMetrics

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

    def test_json_extra_fields(self) -> None:
        """Extra fields passed via logging should appear in JSON output."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test message",
            args=(),
            exc_info=None,
        )
        # Simulate extra fields (how logging.info("msg", extra={...}) works)
        record.suite_name = "demo-suite"  # type: ignore[attr-defined]
        record.case_id = "c1"  # type: ignore[attr-defined]

        output = formatter.format(record)
        parsed = json.loads(output)
        assert "extra" in parsed
        assert parsed["extra"]["suite_name"] == "demo-suite"
        assert parsed["extra"]["case_id"] == "c1"

    def test_json_no_extra_when_none(self) -> None:
        """No extra key when no extra fields are set."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="clean",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        parsed = json.loads(output)
        assert "extra" not in parsed


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

        rc = main(["run", "--suite", str(suite_dir), "--predictions", str(preds)])
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


# ---------------------------------------------------------------------------
# MetricsCollector
# ---------------------------------------------------------------------------


class TestMetricsCollector:
    def test_counter_increment(self) -> None:
        mc = MetricsCollector()
        assert mc.get_counter("tests.passed") == 0
        mc.increment("tests.passed")
        assert mc.get_counter("tests.passed") == 1
        mc.increment("tests.passed", 5)
        assert mc.get_counter("tests.passed") == 6

    def test_counter_returns_new_value(self) -> None:
        mc = MetricsCollector()
        val = mc.increment("x")
        assert val == 1
        val = mc.increment("x", 3)
        assert val == 4

    def test_gauge_set_and_get(self) -> None:
        mc = MetricsCollector()
        assert mc.get_gauge("score.avg") is None
        mc.set_gauge("score.avg", 0.85)
        assert mc.get_gauge("score.avg") == 0.85
        mc.set_gauge("score.avg", 0.92)
        assert mc.get_gauge("score.avg") == 0.92

    def test_timer_context_manager(self) -> None:
        mc = MetricsCollector()
        with mc.timer("suite.run"):
            # Simulate some work
            _ = sum(range(1000))
        durations = mc.get_timer("suite.run")
        assert len(durations) == 1
        assert durations[0] >= 0

    def test_timer_manual_record(self) -> None:
        mc = MetricsCollector()
        mc.record_time("test.case", 0.123)
        mc.record_time("test.case", 0.456)
        durations = mc.get_timer("test.case")
        assert len(durations) == 2
        assert durations[0] == pytest.approx(0.123)
        assert durations[1] == pytest.approx(0.456)

    def test_snapshot(self) -> None:
        mc = MetricsCollector()
        mc.increment("a", 3)
        mc.set_gauge("g", 1.5)
        mc.record_time("t", 0.1)
        mc.record_time("t", 0.2)

        snap = mc.snapshot()
        assert snap["counters"] == {"a": 3}
        assert snap["gauges"]["g"] == pytest.approx(1.5)
        assert snap["timers"]["t"]["count"] == 2
        assert snap["timers"]["t"]["total_seconds"] == pytest.approx(0.3, abs=1e-4)
        assert snap["timers"]["t"]["min_seconds"] == pytest.approx(0.1, abs=1e-4)
        assert snap["timers"]["t"]["max_seconds"] == pytest.approx(0.2, abs=1e-4)

    def test_reset(self) -> None:
        mc = MetricsCollector()
        mc.increment("x")
        mc.set_gauge("y", 1.0)
        mc.record_time("z", 0.5)
        mc.reset()

        assert mc.get_counter("x") == 0
        assert mc.get_gauge("y") is None
        assert mc.get_timer("z") == []
        snap = mc.snapshot()
        assert snap == {"counters": {}, "timers": {}, "gauges": {}}

    def test_snapshot_empty(self) -> None:
        mc = MetricsCollector()
        snap = mc.snapshot()
        assert snap == {"counters": {}, "timers": {}, "gauges": {}}

    def test_snapshot_is_serialisable(self) -> None:
        mc = MetricsCollector()
        mc.increment("count", 10)
        mc.set_gauge("ratio", 0.12345678)
        mc.record_time("op", 1.23456789)
        snap = mc.snapshot()
        # Must not raise
        text = json.dumps(snap)
        parsed = json.loads(text)
        assert parsed["counters"]["count"] == 10


# ---------------------------------------------------------------------------
# SuiteMetrics
# ---------------------------------------------------------------------------


class TestSuiteMetrics:
    def test_record_pass(self) -> None:
        sm = SuiteMetrics()
        sm.record_case(score=1.0, elapsed=0.01)
        assert sm.total_cases == 1
        assert sm.passed == 1
        assert sm.failed == 0
        assert sm.skipped == 0

    def test_record_fail(self) -> None:
        sm = SuiteMetrics()
        sm.record_case(score=0.5, elapsed=0.01)
        assert sm.total_cases == 1
        assert sm.passed == 0
        assert sm.failed == 1

    def test_record_skip(self) -> None:
        sm = SuiteMetrics()
        sm.record_case(score=0.0, elapsed=0.0, skipped=True)
        assert sm.total_cases == 1
        assert sm.skipped == 1
        assert sm.failed == 0
        assert sm.passed == 0

    def test_average_score(self) -> None:
        sm = SuiteMetrics()
        sm.record_case(score=1.0, elapsed=0.01)
        sm.record_case(score=0.5, elapsed=0.02)
        assert sm.average_score == pytest.approx(0.75)

    def test_average_score_empty(self) -> None:
        sm = SuiteMetrics()
        assert sm.average_score == 0.0

    def test_to_dict(self) -> None:
        sm = SuiteMetrics()
        sm.record_case(score=1.0, elapsed=0.01)
        sm.record_case(score=0.0, elapsed=0.02)
        sm.execution_time_seconds = 0.05
        d = sm.to_dict()
        assert d["total_cases"] == 2
        assert d["passed"] == 1
        assert d["failed"] == 1
        assert d["skipped"] == 0
        assert d["average_score"] == pytest.approx(0.5)
        assert d["execution_time_seconds"] == pytest.approx(0.05)

    def test_to_dict_serialisable(self) -> None:
        sm = SuiteMetrics()
        sm.record_case(score=0.75, elapsed=0.1)
        text = json.dumps(sm.to_dict())
        parsed = json.loads(text)
        assert parsed["total_cases"] == 1


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------


class TestHealthCheck:
    def test_health_check_returns_healthy(self) -> None:
        result = check_health()
        assert result["healthy"] is True
        assert isinstance(result["checks"], list)
        assert len(result["checks"]) > 0

    def test_health_check_includes_platform(self) -> None:
        result = check_health()
        assert "platform" in result
        assert "python_version" in result["platform"]
        assert "architecture" in result["platform"]

    def test_health_check_python_version(self) -> None:
        result = check_health()
        py_check = next(c for c in result["checks"] if c["name"] == "python_version")
        assert py_check["ok"] is True
        assert "version" in py_check

    def test_health_check_internal_imports(self) -> None:
        result = check_health()
        import_check = next(c for c in result["checks"] if c["name"] == "internal_imports")
        assert import_check["ok"] is True

    def test_health_check_temp_io(self) -> None:
        result = check_health()
        io_check = next(c for c in result["checks"] if c["name"] == "temp_io")
        assert io_check["ok"] is True

    def test_health_check_cryptography_is_optional(self) -> None:
        result = check_health()
        crypto_check = next(c for c in result["checks"] if c["name"] == "cryptography")
        # Even if cryptography is not installed, health should be True
        # because it's optional.
        assert crypto_check.get("optional") is True

    def test_health_check_serialisable(self) -> None:
        result = check_health()
        text = json.dumps(result)
        parsed = json.loads(text)
        assert parsed["healthy"] is True

    def test_healthy_only_considers_required_checks(self) -> None:
        """The 'healthy' flag ignores optional check failures."""
        result = check_health()
        # Even if cryptography is missing (ok=False), healthy should be True
        # as long as all required checks pass.
        required = [c for c in result["checks"] if not c.get("optional")]
        assert all(c["ok"] for c in required)
        assert result["healthy"] is True


# ---------------------------------------------------------------------------
# Runner structured logging integration
# ---------------------------------------------------------------------------


class TestRunnerLogging:
    def test_runner_logs_suite_lifecycle(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Verify that runner emits structured log messages for suite start/end."""
        suite_dir = tmp_path / "suite"
        suite_dir.mkdir()
        (suite_dir / "suite.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "name": "log-test",
                    "description": "logging test",
                    "created_at": "2025-01-01T00:00:00Z",
                    "scoring": {},
                }
            ),
            encoding="utf-8",
        )
        (suite_dir / "cases.jsonl").write_text(
            json.dumps({"id": "c1", "input": "x", "expected": "y"}) + "\n",
            encoding="utf-8",
        )
        preds = tmp_path / "preds.jsonl"
        preds.write_text(
            json.dumps({"id": "c1", "prediction": "y"}) + "\n",
            encoding="utf-8",
        )

        from toolkit_eval_harness.runner import run_suite
        from toolkit_eval_harness.suite import read_suite_dir

        suite = read_suite_dir(suite_dir)

        with caplog.at_level(logging.DEBUG, logger="toolkit_eval_harness.runner"):
            run_suite(suite=suite, predictions_path=preds)

        messages = caplog.text
        assert "Suite execution started" in messages
        assert "Suite execution finished" in messages
        assert "log-test" in messages

    def test_runner_logs_case_details_at_debug(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Case-level details should appear at DEBUG level."""
        suite_dir = tmp_path / "suite"
        suite_dir.mkdir()
        (suite_dir / "suite.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "name": "case-log",
                    "description": "",
                    "created_at": "2025-01-01",
                    "scoring": {},
                }
            ),
            encoding="utf-8",
        )
        (suite_dir / "cases.jsonl").write_text(
            json.dumps({"id": "c1", "input": "a", "expected": "b"}) + "\n",
            encoding="utf-8",
        )
        preds = tmp_path / "preds.jsonl"
        preds.write_text(
            json.dumps({"id": "c1", "prediction": "b"}) + "\n",
            encoding="utf-8",
        )

        from toolkit_eval_harness.runner import run_suite
        from toolkit_eval_harness.suite import read_suite_dir

        suite = read_suite_dir(suite_dir)

        with caplog.at_level(logging.DEBUG, logger="toolkit_eval_harness.runner"):
            run_suite(suite=suite, predictions_path=preds)

        assert "Case c1" in caplog.text
