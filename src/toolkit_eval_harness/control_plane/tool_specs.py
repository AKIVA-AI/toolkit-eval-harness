"""
CLI command → ToolSpec mapping for toolkit-eval-harness.

Maps the 7 top-level CLI subcommands to ToolSpec contracts.

All commands are READ_ONLY + AUTO — the eval harness reads prediction files,
runs scoring, and produces reports but never modifies external state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import ApprovalPolicy, AuthorityBoundary, PermissionScope, ToolSpec


@dataclass
class ToolkitCommandSpec:
    """Maps a CLI subcommand name to its ToolSpec and authority boundary."""

    command: str
    spec: ToolSpec
    boundary: AuthorityBoundary


def _make_spec(name: str, description: str, input_schema: dict[str, Any] | None = None) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        category="tool",
        version="1.0.0",
        owner="toolkit-eval-harness",
        permission_scope=PermissionScope.READ_ONLY,
        input_schema=input_schema,
        output_schema=None,
        sandbox_requirement=None,
        aliases=None,
    )


_READ_ONLY_AUTO = AuthorityBoundary(scope=PermissionScope.READ_ONLY, approval=ApprovalPolicy.AUTO)

# ── Per-command specs ─────────────────────────────────────────────────────────

TOOLKIT_TOOL_SPECS: dict[str, ToolkitCommandSpec] = {
    "keygen": ToolkitCommandSpec(
        command="keygen",
        spec=_make_spec(
            name="keygen",
            description="Generate an Ed25519 keypair for signing suite packs.",
            input_schema={
                "type": "object",
                "properties": {
                    "output_dir": {
                        "type": "string",
                        "description": "Directory to write keypair files",
                    },
                },
            },
        ),
        boundary=_READ_ONLY_AUTO,
    ),
    "pack": ToolkitCommandSpec(
        command="pack",
        spec=_make_spec(
            name="pack",
            description=(
                "Suite pack utilities: create, inspect, verify, sign, and verify-signature. "
                "Operates on suite zip archives."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "pack_cmd": {
                        "type": "string",
                        "enum": ["create", "inspect", "verify", "sign", "verify-signature"],
                    },
                    "suite_path": {"type": "string"},
                },
                "required": ["pack_cmd"],
            },
        ),
        boundary=_READ_ONLY_AUTO,
    ),
    "run": ToolkitCommandSpec(
        command="run",
        spec=_make_spec(
            name="run",
            description="Run an evaluation suite against predictions and produce a scored report.",
            input_schema={
                "type": "object",
                "properties": {
                    "suite": {"type": "string", "description": "Path to suite directory or zip"},
                    "predictions": {"type": "string", "description": "Path to predictions JSONL"},
                    "output": {"type": "string", "description": "Output report path"},
                    "format": {"type": "string", "enum": ["json", "text", "markdown"]},
                    "workers": {"type": "integer"},
                    "fail_fast": {"type": "boolean"},
                },
                "required": ["suite", "predictions"],
            },
        ),
        boundary=_READ_ONLY_AUTO,
    ),
    "compare": ToolkitCommandSpec(
        command="compare",
        spec=_make_spec(
            name="compare",
            description="Compare a candidate eval report against a baseline report.",
            input_schema={
                "type": "object",
                "properties": {
                    "baseline": {"type": "string"},
                    "candidate": {"type": "string"},
                    "format": {"type": "string", "enum": ["json", "text"]},
                },
                "required": ["baseline", "candidate"],
            },
        ),
        boundary=_READ_ONLY_AUTO,
    ),
    "validate-report": ToolkitCommandSpec(
        command="validate-report",
        spec=_make_spec(
            name="validate-report",
            description="Validate that an eval report JSON has the expected schema shape.",
            input_schema={
                "type": "object",
                "properties": {
                    "report": {"type": "string", "description": "Path to report JSON"},
                },
                "required": ["report"],
            },
        ),
        boundary=_READ_ONLY_AUTO,
    ),
    "check-deps": ToolkitCommandSpec(
        command="check-deps",
        spec=_make_spec(
            name="check-deps",
            description="Verify all required tools and dependencies are available.",
            input_schema=None,
        ),
        boundary=_READ_ONLY_AUTO,
    ),
}


def get_tool_spec(command: str) -> ToolkitCommandSpec | None:
    """Return the ToolkitCommandSpec for a CLI subcommand, or None if unknown."""
    return TOOLKIT_TOOL_SPECS.get(command)


__all__ = ["TOOLKIT_TOOL_SPECS", "ToolkitCommandSpec", "get_tool_spec"]
