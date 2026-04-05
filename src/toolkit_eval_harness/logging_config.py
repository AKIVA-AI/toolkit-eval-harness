"""Structured logging configuration for toolkit-eval-harness.

Supports two output formats:
- text: human-readable ``timestamp | LEVEL | message``
- json: machine-parseable JSON lines (one object per log record)

Both formats write to *stderr* so that stdout remains reserved for
command output (JSON reports, etc.).

The JSON formatter automatically includes any ``extra`` fields attached
to the log record, making it suitable for structured observability
(correlation IDs, metric snapshots, etc.).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# Fields that belong to the standard LogRecord and should NOT be
# forwarded as user-supplied ``extra`` data in JSON output.
_BUILTIN_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys() | {"message", "asctime"}
)


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON objects.

    Any ``extra`` keyword arguments passed to the logging call are
    included under an ``"extra"`` key, enabling structured fields such as
    ``suite_name``, ``case_id``, or ``correlation_id``.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        # Capture any extra fields the caller attached.
        extra: dict[str, Any] = {
            k: v for k, v in record.__dict__.items() if k not in _BUILTIN_ATTRS
        }
        if extra:
            log_entry["extra"] = extra

        return json.dumps(log_entry, default=str)


TEXT_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
TEXT_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(
    *, level: int = logging.WARNING, fmt: str = "text", log_file: str = ""
) -> None:
    """Configure the root logger.

    Args:
        level: Logging level (e.g. ``logging.DEBUG``).
        fmt: ``"text"`` for human-readable or ``"json"`` for JSON lines.
        log_file: Optional file path to write logs to (in addition to stderr).
    """
    root = logging.getLogger()
    # Remove existing handlers to avoid duplicate output on re-init.
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    formatter: logging.Formatter
    if fmt == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(TEXT_FORMAT, datefmt=TEXT_DATEFMT)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    root.addHandler(stderr_handler)

    if log_file:
        from pathlib import Path

        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    root.setLevel(level)
