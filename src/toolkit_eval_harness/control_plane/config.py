"""
Config hierarchy contract for toolkit-eval-harness.

Three-tier hierarchy (mirrors Akiva platform pattern):
  Level 0 — Platform defaults (global Akiva CLI conventions)
  Level 1 — Toolkit config (pyproject.toml / config file)
  Level 2 — CLI overrides (argv flags)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolkitConfigContract:
    """
    Resolved configuration contract for toolkit-eval-harness.

    All fields represent resolved values after applying the three-tier
    hierarchy (platform defaults → toolkit config → CLI overrides).
    """

    # ── Identity ──────────────────────────────────────────────────────────────
    toolkit_id: str = "TK-03"
    toolkit_name: str = "toolkit-eval-harness"
    version: str = "1.0.0"

    # ── Runtime behaviour ─────────────────────────────────────────────────────
    log_format: str = "json"  # 'json' | 'text'
    structured_logging: bool = True
    output_format: str = "json"  # 'json' | 'text' | 'markdown'

    # ── Eval-harness specific ─────────────────────────────────────────────────
    max_workers: int = 4  # parallel evaluation workers
    fail_fast: bool = False  # stop on first failure
    coverage_threshold: float = 0.0  # minimum eval coverage 0.0–1.0

    # ── Extension ─────────────────────────────────────────────────────────────
    extra: dict[str, Any] = field(default_factory=dict)


CONFIG_LEVELS = {
    "platform_default": 0,
    "toolkit_config": 1,
    "cli_override": 2,
}


def build_config_hierarchy(
    toolkit_config: dict[str, Any] | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> ToolkitConfigContract:
    """
    Merge config tiers into a resolved ToolkitConfigContract.

    Priority: CLI overrides > toolkit config > platform defaults.
    """
    resolved: dict[str, Any] = {
        "toolkit_id": "TK-03",
        "toolkit_name": "toolkit-eval-harness",
        "version": "1.0.0",
        "log_format": "json",
        "structured_logging": True,
        "output_format": "json",
        "max_workers": 4,
        "fail_fast": False,
        "coverage_threshold": 0.0,
        "extra": {},
    }

    if toolkit_config:
        for k, v in toolkit_config.items():
            if k in resolved:
                resolved[k] = v
            else:
                resolved["extra"][k] = v

    if cli_overrides:
        for k, v in cli_overrides.items():
            if k in resolved:
                resolved[k] = v
            else:
                resolved["extra"][k] = v

    return ToolkitConfigContract(**{k: v for k, v in resolved.items()})


__all__ = ["ToolkitConfigContract", "CONFIG_LEVELS", "build_config_hierarchy"]
