# toolkit-eval-harness: design principles

**Primary user:** engineers who evaluate model outputs in CI.
**Core purpose:** deterministic scoring of predictions against versioned golden suites, with
CI gating.

## Invariants

1. **Zero runtime dependencies.** The core package installs and runs with the standard
   library only. Optional features (signing) use extras.
2. **Deterministic scoring.** The same suite and predictions always produce the same report
   (apart from timing fields). No network calls or model inference in the default
   scoring path: the `embedding` and `llm_judge` scorers are opt-in per run
   (`--allow-network-scorers`) and record their model and prompts in the report. The only randomness is the `compare` bootstrap, which uses a seeded RNG.
3. **File-based I/O.** Suites, predictions and reports are files (JSON, JSONL, zip).
4. **Immutable data.** `EvalCase`, `EvalSuite`, `EvalReport`, `CompareBudget` and
   `JSONSchema` are frozen dataclasses.
5. **Stdout for data, stderr for logs.**
6. **Packs are checked before use.** Every pack load checks the manifest; `run` also checks
   the signature when one is supplied or sits next to the pack. Extraction validates member
   paths against the destination directory.

## Non-negotiables

1. **Correctness over leniency.** A case passes only if every required scorer passes. A
   false pass in CI is a critical defect.
2. **Reliable exit codes.** `run` exits non-zero when any case fails; see README
   "Exit codes".
3. **Plugin failures fail the case, not the run.** A plugin that raises or returns an
   out-of-range score scores 0.0 for that case, and the run continues.

## Failure-mode boundaries

1. **No silent partial results.** Missing predictions fail their cases and are counted;
   malformed input stops the run with an error.
2. **No code execution from suites.** Suites are data. The scoring path never uses `eval`,
   `exec` or `pickle` on suite content.
3. **No implicit writes.** Commands write only to paths the user names (`--out`,
   `--output`, key paths). Loading a pack writes nothing to disk.
