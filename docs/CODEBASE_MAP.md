# toolkit-eval-harness — Codebase Map

**Created:** 2026-03-18
**Updated:** 2026-04-04
**System:** toolkit-eval-harness (Archetype 9 — Developer Tool / CLI)
**Audit Score:** 72.1/100 (2026-04-04, Build Standard v2.14)
**Purpose:** AI-readable structural map of the live repository.

---

## Directory Structure

```text
toolkit-eval-harness/
|-- src/
|   `-- toolkit_eval_harness/          # 14 Python source files (core)
|       |-- cli.py                     # CLI entrypoint (argparse, 7 subcommands)
|       |-- __main__.py                # python -m entry point
|       |-- __init__.py                # Public API exports (__all__, version)
|       |-- py.typed                   # PEP 561 typed package marker
|       |-- suite.py                   # EvalSuite / EvalCase frozen dataclasses + JSONL loader
|       |-- runner.py                  # run_suite() — scores predictions via built-in + plugin scorers
|       |-- scoring.py                 # exact_match, json_required_keys, JSONSchema validation
|       |-- report.py                  # EvalReport dataclass + JSON serialization
|       |-- compare.py                 # compare_reports() regression gate (CompareBudget)
|       |-- pack.py                    # create/verify/extract .zip suite packs; SHA-256 manifest
|       |-- hashing.py                 # sha256_file() utility (streaming 1MB chunks)
|       |-- signing.py                 # Ed25519 keypair, sign_bytes, verify_bytes (optional dep)
|       |-- plugins.py                 # Scorer plugin registry (entry-point discovery + programmatic)
|       |-- formatters.py              # Output formatters (JSON, table, CSV)
|       |-- io.py                      # File I/O helpers with path validation
|       |-- logging_config.py          # Structured logging setup (JSON + text, log-file support)
|       |-- metrics.py                 # MetricsCollector (thread-safe counters/timers/gauges), SuiteMetrics
|       |-- health.py                  # check_health() — 4 environment checks
|       `-- control_plane/             # Archetype 9 control-plane adapter (3 modules)
|           |-- __init__.py
|           |-- contracts.py           # ToolSpec, AuthorityBoundary, PermissionScope (framework fallback)
|           |-- config.py              # ToolkitConfigContract, config hierarchy
|           `-- tool_specs.py          # ToolSpec mapping for all 7 CLI commands
|-- tests/                             # 12 test modules (190 tests)
|   |-- conftest.py
|   |-- test_adversarial.py            # 19 tests — injection, bounds, manipulation
|   |-- test_cli.py                    # 3 tests — full workflow integration
|   |-- test_compare_and_scoring.py    # 5 tests — regression + scoring
|   |-- test_comprehensive.py          # 46 tests — all scorer types + edge cases
|   |-- test_control_plane.py          # 26 tests — ToolSpec, config, authority
|   |-- test_enhancements.py           # 30 tests — path validation, I/O
|   |-- test_formatters.py             # 9 tests — JSON/table/CSV output
|   |-- test_observability.py          # 41 tests — logging, metrics, health
|   |-- test_pack_and_run.py           # 1 test — pack→run integration
|   |-- test_pack_load_twice.py        # 1 test — idempotent extract
|   `-- test_plugins.py               # 9 tests — registry, entry-points, contract
|-- docs/
|   |-- CODEBASE_MAP.md                # This file
|   |-- SYSTEM_CONSTITUTION.md         # Architectural invariants
|   `-- audits/
|       |-- EVAL_HARNESS_AUDIT_REPORT_2026-03-09.md  # Initial audit (62/100)
|       `-- EVAL_HARNESS_FULL_AUDIT_2026-04-04.md    # Current audit (72.1/100)
|-- .github/
|   |-- workflows/ci.yml               # CI: test matrix (3.10-3.12), security, lint, SBOM, build
|   `-- dependabot.yml                 # pip + github-actions weekly
|-- .env.example
|-- SECURITY.md
|-- CONTRIBUTING.md
|-- CHANGELOG.md
|-- README.md
|-- LICENSE
|-- Dockerfile                         # Multi-stage build (builder + prod)
|-- docker-compose.yml
|-- pyproject.toml
`-- requirements-dev.txt
```

---

## Core Modules

| Module | LOC | Responsibility |
|--------|-----|----------------|
| `cli.py` | 652 | CLI entry point; 7 subcommands: keygen, pack (create/inspect/verify/sign/verify-signature), run, compare, validate-report, check-deps |
| `suite.py` | 65 | `EvalCase` / `EvalSuite` frozen dataclasses; `read_suite_dir()` loads suite.json + cases.jsonl |
| `runner.py` | 115 | `run_suite()` — iterates cases, applies exact-match + JSON-schema + plugin scorers, returns EvalReport |
| `scoring.py` | 90 | `exact_match_score()`, `json_required_keys_score()`, `validate_json()`, `JSONSchema` dataclass |
| `report.py` | 28 | `EvalReport` frozen dataclass with `to_dict()` / `from_dict()` |
| `compare.py` | 36 | `compare_reports()` regression gate — fails if candidate regresses beyond `CompareBudget.max_score_regression_pct` (default 2%) |
| `pack.py` | 110 | Creates/extracts/verifies .zip suite packs with SHA-256 manifest; ZipSlip-protected extraction |
| `hashing.py` | 12 | `sha256_file()` utility with streaming 1MB chunks |
| `signing.py` | 70 | Optional Ed25519 sign/verify (requires `cryptography` extra) |
| `plugins.py` | 166 | Entry-point-based scorer plugin registry; `ScorerFunc` Protocol contract |
| `formatters.py` | 150 | Report output formatters (JSON, table, CSV) |
| `io.py` | 265 | File I/O helpers with path validation (read/write guards) |
| `logging_config.py` | 95 | `JSONFormatter`, `setup_logging()` with text/JSON/log-file support |
| `metrics.py` | 191 | Thread-safe `MetricsCollector` (counters, timers, gauges) + `SuiteMetrics` aggregation |
| `health.py` | 137 | `check_health()` — Python version, internal imports, temp I/O, optional crypto |
| `control_plane/` | 407 | `ToolSpec`, `AuthorityBoundary`, `PermissionScope`, config hierarchy; optional framework import |

---

## Test Coverage

| Suite | Files | Tests |
|-------|-------|-------|
| Core unit + integration tests | 12 modules | 190 |
| Coverage threshold | — | 80% (enforced in CI) |

---

## Data Flow

```
suite/ (dir or .zip)
  suite.json        <- name, scoring config, schema_version
  cases.jsonl       <- {id, input, expected, tags} per line

predictions.jsonl   <- {id, prediction} per line (model output)

run_suite()
  -> load predictions into dict
  -> for each case: apply built-in scorers + plugin scorers
  -> collect MetricsCollector timing + SuiteMetrics aggregation
  -> EvalReport {suite, summary:{cases, score}, cases:[{id, score, exact, json, plugins}]}

compare_reports()
  -> pass/fail based on regression_pct <= max_score_regression_pct
```

---

## Dependencies

**Runtime:** Zero (stdlib only)
**Optional:** `cryptography>=43.0.0` (Ed25519 signing)
**Dev:** pytest, pytest-cov, ruff, pyright, cryptography

---

## Known Gaps (from 2026-04-04 audit)

- Plugin scorers wired into runner but no RAGAS-aligned scorer implementations yet
- No parallel evaluation (PARALLEL_WORKERS config exists but not implemented)
- No shell completion (bash/zsh/fish)
- Docker base image `python:3.11-slim` has upstream HIGH vulnerability (human action)
- No PyPI publishing workflow
- No signed releases
