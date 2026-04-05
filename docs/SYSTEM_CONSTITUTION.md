# toolkit-eval-harness — System Constitution

**Created:** 2026-04-04
**Archetype:** 9 — Developer Tool / CLI
**Primary User:** AI/ML engineers evaluating model outputs in CI pipelines
**Core Purpose:** Deterministic scoring of AI predictions against versioned golden test suites with regression gating.

---

## Architectural Invariants

1. **Zero runtime dependencies.** The core package must install and run with stdlib only. Optional features (signing) use extras.
2. **Deterministic scoring.** Given the same suite + predictions, `run_suite()` must produce identical scores every time. No randomness, no network calls, no LLM inference in the scoring path.
3. **File-based I/O only.** Suites, predictions, and reports are files (JSON, JSONL, ZIP). No database, no API server, no network required for core operations.
4. **Immutable data structures.** `EvalCase`, `EvalSuite`, `EvalReport`, `CompareBudget`, `JSONSchema` are frozen dataclasses. Mutation is a bug.
5. **Stdout for data, stderr for logs.** CLI output (reports, JSON) goes to stdout. Logging goes to stderr. Mixing is a bug.
6. **Pack integrity is non-negotiable.** Every pack extraction validates member paths against the destination directory (ZipSlip protection). Every pack verification checks SHA-256 hashes against the manifest.

## Non-Negotiables

1. **Scoring correctness over speed.** A wrong score is worse than a slow score. No optimization may sacrifice correctness.
2. **CI exit codes must be reliable.** Exit 0 = success, exit 4 = regression/validation failure. A false-positive pass in CI is a critical defect.
3. **Plugin scorers cannot crash the pipeline.** Plugin scorer exceptions are caught, logged, and scored as 0.0. The pipeline continues.
4. **Path validation on all file I/O.** Every file read/write operation goes through `io.py` validation functions. Direct `open()` calls outside `io.py` are prohibited.

## Failure Mode Boundaries

1. **Never silently produce partial results.** If a suite cannot be fully scored, fail with a clear error rather than returning a partial report.
2. **Never execute untrusted code from suites.** Suites contain data (JSON/JSONL), never executable code. The scoring path must not `eval()`, `exec()`, or `pickle.load()` any suite content.
3. **Never write outside the specified output path.** Pack extraction, report writing, and key generation respect the user-specified destination. No implicit writes to CWD or temp directories that leak state.
