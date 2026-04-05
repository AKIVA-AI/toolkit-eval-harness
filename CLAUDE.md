# Eval Harness — Golden task evaluation suites with deterministic scoring and CI regression

**Archetype:** 9 — Developer Tool / CLI Utility
**Standards:** Akiva Build Standard v2.14
**Ontology ID:** TK-03

## Stack
- Language: Python 3.10+
- Test: `pytest -xvs`
- Lint: `ruff check src/ tests/`
- Build: `pip install -e .`

## Verification Commands
| Command | Purpose |
|---------|---------|
| `pytest -xvs` | Run tests |
| `ruff check src/ tests/` | Lint |

## Current State
- Audit Score: 75.4/100 (2026-04-04, Build Standard v2.14, post-remediation)
- Prior Audit: 62/100 (2026-03-09, Build Standard v1.2)
- Tests: 208
- Coverage: 81.97%
- Source LOC: 2,583
- Test LOC: 2,405

## Key Rules
- Archetype 9: single-purpose CLI tool, zero or minimal dependencies in core
- Tests first, security fixes before features
- One task at a time, verified before moving to next
