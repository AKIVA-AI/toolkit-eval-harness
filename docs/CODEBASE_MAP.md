# toolkit-eval-harness — Codebase Map

**Created:** 2026-03-18
**Updated:** 2026-03-18
**System:** toolkit-eval-harness (Archetype 9 — Developer Tool / CLI)
**Audit Score:** ~72/100 (estimated; D10 Security = 6/10 per 2026-03-09 benchmark; adversarial tests added S20)
**Purpose:** AI-readable structural map of the live repository.

---

## Directory Structure

```text
toolkit-eval-harness/
|-- src/
|   `-- toolkit_eval_harness/          # 15 Python source files
|       |-- cli.py                     # CLI entrypoint (argparse)
|       |-- __main__.py                # python -m entry point
|       |-- __init__.py
|       |-- py.typed
|       |-- suite.py                   # EvalSuite / EvalCase data structures + JSONL loader
|       |-- runner.py                  # run_suite() — scores predictions against a suite
|       |-- scoring.py                 # exact_match, json_required_keys, JSONSchema validation
|       |-- report.py                  # EvalReport dataclass + JSON serialization
|       |-- compare.py                 # compare_reports() regression gate (CompareBudget)
|       |-- pack.py                    # create/verify/extract .zip suite packs; SHA-256 manifest
|       |-- hashing.py                 # sha256_file() utility
|       |-- signing.py                 # Ed25519 keypair, sign_bytes, verify_bytes (optional dep)
|       |-- plugins.py                 # Scorer plugin registry (entry-point discovery)
|       |-- formatters.py              # Output formatters (JSON, text)
|       |-- io.py                      # File I/O helpers
|       `-- logging_config.py          # Structured logging setup
|-- tests/                             # 11 test modules (154 tests)
|   |-- conftest.py
|   |-- test_adversarial.py            # Adversarial / boundary input tests (added S20)
|   |-- test_cli.py
|   |-- test_compare_and_scoring.py
|   |-- test_comprehensive.py
|   |-- test_enhancements.py
|   |-- test_formatters.py
|   |-- test_observability.py
|   |-- test_pack_and_run.py
|   |-- test_pack_load_twice.py
|   `-- test_plugins.py
|-- docs/
|   `-- CODEBASE_MAP.md                # This file
|-- .env.example
|-- SECURITY.md
|-- requirements-dev.txt
`-- pyproject.toml (inferred)
```

---

## Core Modules

| Module | Responsibility |
|--------|---------------|
| `cli.py` | CLI entry point; `run`, `compare`, `pack`, `verify` sub-commands |
| `suite.py` | `EvalCase` / `EvalSuite` frozen dataclasses; `read_suite_dir()` loads `suite.json` + `cases.jsonl` |
| `runner.py` | `run_suite()` — iterates cases, applies exact-match and JSON-schema scoring, returns `EvalReport` |
| `scoring.py` | `exact_match_score()`, `json_required_keys_score()`, `validate_json()`, `JSONSchema` dataclass |
| `report.py` | `EvalReport` dataclass with `to_dict()` / `from_dict()`; `write_report_json()` |
| `compare.py` | `compare_reports()` regression gate — fails if candidate score regresses beyond `CompareBudget.max_score_regression_pct` (default 2%) |
| `pack.py` | Creates/extracts/verifies `.zip` suite packs with SHA-256 manifest; `load_suite_from_path()` handles dir or zip |
| `hashing.py` | `sha256_file()` utility used by pack integrity verification |
| `signing.py` | Optional Ed25519 sign/verify for artifact provenance (requires `cryptography` extra) |
| `plugins.py` | Entry-point-based scorer plugin registry; `list_scorers()` enumerates installed scorers |
| `formatters.py` | Report output formatters (JSON, human-readable text) |
| `logging_config.py` | Structured logging configuration |

---

## Test Coverage

| Suite | Files | Tests |
|-------|-------|-------|
| Core unit tests | 10 modules | 154 (post-S20) |
| Coverage target | — | 88% |

---

## Data Flow

```
suite/ (dir or .zip)
  suite.json        ← name, scoring config, schema_version
  cases.jsonl       ← {id, input, expected, tags} per line

predictions.jsonl   ← {id, prediction} per line (model output)

run_suite()
  → EvalReport      ← {suite, summary:{cases, score}, cases:[{id, score, exact, json}]}

compare_reports()
  → pass/fail       ← regression_pct ≤ max_score_regression_pct
```

---

## Known Gaps (from ~2026-03-09 benchmark)

- D10 (Security) = 6/10 — below Build Standard D4 minimum of 7; adversarial tests added S20 improve posture; re-audit warranted
- D2 (Multi-Tenancy) = 3/10 — CLI tool architecture, by design
- No automated SBOM/CVE scanning in CI
- `signing.py` requires optional `cryptography` dependency — not enforced in base install
