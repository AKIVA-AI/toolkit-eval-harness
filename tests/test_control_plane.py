"""
Tests for toolkit-eval-harness control_plane adapter.

Coverage:
  - contracts: PermissionScope, ApprovalPolicy, AuthorityBoundary, ToolSpec, framework flag
  - config: build_config_hierarchy (defaults, toolkit config, CLI overrides)
  - tool_specs: TOOLKIT_TOOL_SPECS covers all 6 commands, get_tool_spec lookup
"""

from __future__ import annotations

from toolkit_eval_harness.control_plane.config import (
    CONFIG_LEVELS,
    ToolkitConfigContract,
    build_config_hierarchy,
)
from toolkit_eval_harness.control_plane.contracts import (
    _HAS_EXECUTION_CONTRACTS,
    ApprovalPolicy,
    AuthorityBoundary,
    PermissionScope,
)
from toolkit_eval_harness.control_plane.tool_specs import (
    TOOLKIT_TOOL_SPECS,
    get_tool_spec,
)

# ── contracts ─────────────────────────────────────────────────────────────────


class TestPermissionScope:
    def test_values(self) -> None:
        assert PermissionScope.READ_ONLY.value == "read_only"
        assert PermissionScope.WORKSPACE_WRITE.value == "workspace_write"
        assert PermissionScope.FULL_ACCESS.value == "full_access"


class TestAuthorityBoundary:
    def test_is_denied(self) -> None:
        b = AuthorityBoundary(scope=PermissionScope.READ_ONLY, approval=ApprovalPolicy.DENY)
        assert b.is_denied()

    def test_needs_approval(self) -> None:
        b = AuthorityBoundary(
            scope=PermissionScope.FULL_ACCESS, approval=ApprovalPolicy.REQUIRE_APPROVAL
        )
        assert b.needs_approval()

    def test_auto_neither(self) -> None:
        b = AuthorityBoundary(scope=PermissionScope.READ_ONLY, approval=ApprovalPolicy.AUTO)
        assert not b.is_denied()
        assert not b.needs_approval()

    def test_scope_allows_equal(self) -> None:
        b = AuthorityBoundary(scope=PermissionScope.WORKSPACE_WRITE, approval=ApprovalPolicy.AUTO)
        assert b.scope_allows(PermissionScope.READ_ONLY)
        assert b.scope_allows(PermissionScope.WORKSPACE_WRITE)
        assert not b.scope_allows(PermissionScope.FULL_ACCESS)


class TestFrameworkFlag:
    def test_flag_is_bool(self) -> None:
        assert isinstance(_HAS_EXECUTION_CONTRACTS, bool)


# ── config ────────────────────────────────────────────────────────────────────


class TestConfigLevels:
    def test_ordering(self) -> None:
        assert CONFIG_LEVELS["platform_default"] < CONFIG_LEVELS["toolkit_config"]
        assert CONFIG_LEVELS["toolkit_config"] < CONFIG_LEVELS["cli_override"]


class TestBuildConfigHierarchy:
    def test_defaults(self) -> None:
        cfg = build_config_hierarchy()
        assert cfg.toolkit_id == "TK-03"
        assert cfg.toolkit_name == "toolkit-eval-harness"
        assert cfg.max_workers == 4
        assert cfg.fail_fast is False
        assert cfg.coverage_threshold == 0.0

    def test_toolkit_config_overrides_defaults(self) -> None:
        cfg = build_config_hierarchy(toolkit_config={"max_workers": 8, "fail_fast": True})
        assert cfg.max_workers == 8
        assert cfg.fail_fast is True

    def test_cli_overrides_toolkit_config(self) -> None:
        cfg = build_config_hierarchy(
            toolkit_config={"max_workers": 8},
            cli_overrides={"max_workers": 2},
        )
        assert cfg.max_workers == 2

    def test_unknown_keys_go_to_extra(self) -> None:
        cfg = build_config_hierarchy(cli_overrides={"custom_key": "value"})
        assert cfg.extra.get("custom_key") == "value"

    def test_returns_correct_type(self) -> None:
        assert isinstance(build_config_hierarchy(), ToolkitConfigContract)


# ── tool_specs ────────────────────────────────────────────────────────────────


class TestToolkitToolSpecs:
    EXPECTED_COMMANDS = {"keygen", "pack", "run", "compare", "validate-report", "check-deps"}

    def test_all_commands_present(self) -> None:
        assert set(TOOLKIT_TOOL_SPECS.keys()) == self.EXPECTED_COMMANDS

    def test_all_commands_are_read_only(self) -> None:
        for name, cmd in TOOLKIT_TOOL_SPECS.items():
            assert cmd.spec.permission_scope == PermissionScope.READ_ONLY, name

    def test_all_commands_auto_approval(self) -> None:
        for name, cmd in TOOLKIT_TOOL_SPECS.items():
            assert cmd.boundary.approval == ApprovalPolicy.AUTO, name

    def test_boundary_scope_matches_spec(self) -> None:
        for name, cmd in TOOLKIT_TOOL_SPECS.items():
            assert cmd.boundary.scope == cmd.spec.permission_scope, name

    def test_no_sandbox_required(self) -> None:
        for name, cmd in TOOLKIT_TOOL_SPECS.items():
            assert cmd.spec.sandbox_requirement is None, name

    def test_command_key_matches_command_field(self) -> None:
        for key, cmd in TOOLKIT_TOOL_SPECS.items():
            assert cmd.command == key

    def test_owner_is_toolkit(self) -> None:
        for cmd in TOOLKIT_TOOL_SPECS.values():
            assert cmd.spec.owner == "toolkit-eval-harness"

    def test_run_requires_suite_and_predictions(self) -> None:
        schema = TOOLKIT_TOOL_SPECS["run"].spec.input_schema
        assert schema is not None
        required = schema.get("required", [])
        assert "suite" in required
        assert "predictions" in required

    def test_compare_requires_baseline_and_candidate(self) -> None:
        schema = TOOLKIT_TOOL_SPECS["compare"].spec.input_schema
        assert schema is not None
        required = schema.get("required", [])
        assert "baseline" in required
        assert "candidate" in required

    def test_pack_has_pack_cmd_enum(self) -> None:
        schema = TOOLKIT_TOOL_SPECS["pack"].spec.input_schema
        assert schema is not None
        pack_cmd_prop = schema.get("properties", {}).get("pack_cmd", {})
        assert "create" in pack_cmd_prop.get("enum", [])

    def test_check_deps_has_no_required_inputs(self) -> None:
        cmd = TOOLKIT_TOOL_SPECS["check-deps"]
        # check-deps takes no arguments — input_schema may be None
        assert cmd.spec.input_schema is None or cmd.spec.input_schema.get("required", []) == []


class TestGetToolSpec:
    def test_returns_spec_for_known_command(self) -> None:
        spec = get_tool_spec("run")
        assert spec is not None
        assert spec.command == "run"

    def test_returns_none_for_unknown(self) -> None:
        assert get_tool_spec("nonexistent") is None

    def test_returns_none_for_empty_string(self) -> None:
        assert get_tool_spec("") is None
