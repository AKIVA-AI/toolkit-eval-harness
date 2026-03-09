"""Structured logging configuration for toolkit-eval-harness.

Supports two output formats:
- text: human-readable ``timestamp | LEVEL | message``
- json: machine-parseable JSON lines (one object per log record)

Both formats write to *stderr* so that stdout remains reserved for
command output (JSON reports, etc.).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JSONFormatter(logging.Formatter):
    """Format log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info and record.exc_info[1] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry, default=str)


TEXT_FORMAT = "%(asctime)s | %(levelname)-8s | %(message)s"
TEXT_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(*, level: int = logging.WARNING, fmt: str = "text") -> None:
    """Configure the root logger.

    Args:
        level: Logging level (e.g. ``logging.DEBUG``).
        fmt: ``"text"`` for human-readable or ``"json"`` for JSON lines.
    """
    root = logging.getLogger()
    # Remove existing handlers to avoid duplicate output on re-init.
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stderr)
    if fmt == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(TEXT_FORMAT, datefmt=TEXT_DATEFMT))

    root.setLevel(level)
    root.addHandler(handler)
