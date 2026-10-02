# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.0] - 2026-09-26

First stable release: an eval regression gate with signed evidence. First release on PyPI
(published 2026-10-02): `pip install toolkit-eval-harness`.

### Release and project files

- `schemas/report-envelope.v1.json` is now byte-identical to the shared copy used across the toolkit repos.
- Release workflow: a `v*` tag runs the tests, builds the sdist and wheel,
  checks them with `twine check --strict` (twine 6.1 or newer, which reads the
  Metadata 2.4 that setuptools 77+ writes), installs the wheel and checks its
  version against the tag, and attaches both files to a GitHub Release. The
  PyPI upload (Trusted Publishing) runs only when the repository variable
  `PUBLISH_TO_PYPI` is `true`. See `RELEASING.md`.
- CI builds and checks the package the same way on every pull request.
- Package metadata: SPDX license expression `Apache-2.0` with `LICENSE` and
  `NOTICE` in the distributions, author AKIVA AI, LLC, and links to the
  documentation, issues and changelog.
- Added `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1), issue and pull request
  templates and `RELEASING.md`. `SECURITY.md` lists the supported versions and
  the private reporting channel.
- CI runs pyright, and `pip-audit` with every optional extra installed instead
  of the retired `safety check`.

### Added
- `examples/gsm8k-20/`: the README's 5-minute example on the first 20 GSM8K test problems.
- **Report envelope.** `run --out` and the new `compare --out` write an in-toto Statement v1
  in canonical JSON (`eval.run` / `eval.compare`), with a `pass`/`fail`/`error` verdict that
  matches the exit code. Spec: `docs/report-envelope.md`; schema:
  `schemas/report-envelope.v1.json`. `validate-report` checks envelopes, and `compare` and
  `EvalReport.from_dict()` read them.
- `EvalSuite.content_digest()` and `suite.sha256` in reports: a packaging-independent SHA-256
  of the suite content.
- A pack that fails verification during `run --out` produces an `error` envelope whose subject
  is the pack file.
- `SOURCE_DATE_EPOCH` fixes the report timestamp for reproducible reports.

- **Statistically sound `compare`.** Per-case flip detection (`new_failures`, `fixes`),
  per-tag breakdown, and a seeded paired percentile-bootstrap confidence interval on the mean
  score delta (`--confidence`, `--iterations`, `--seed`; validated against
  `scipy.stats.bootstrap`). `--max-new-failures` adds a flip gate. `CompareBudget` gains
  `method`, `confidence`, `iterations`, `seed`, `max_new_failures` and `allow_suite_mismatch`,
  all with defaults.
- **GitHub Action** (`action.yml`, composite): runs `compare`, writes the `eval.compare`
  envelope and a Markdown job summary, optionally comments on the PR, exposes
  `verdict`/`exit-code` outputs and fails the step on a failed gate. Self-tested by
  `.github/workflows/action-selftest.yml`.
- `--format markdown` for compare results and reports.
- **Built-in scorers:** `normalized_exact` and `token_f1` (SQuAD v1.1 definitions), `fuzzy`
  (Levenshtein similarity), `regex`, `numeric` (`math.isclose` tolerances, number
  extraction), `json_schema` (real JSON Schema validation, `jsonschema` extra), and opt-in
  `embedding` and `llm_judge` scorers through LiteLLM (`judge` extra). `scoring.scorers`
  entries can be objects with options and a `label`. Network scorers are refused unless
  `run --allow-network-scorers` (`run_suite(allow_network_scorers=True)`) is given; the judge's
  model, prompt, rubric and replies are recorded in the report.
- **Importers.** `toolkit-eval import promptfoo|inspect|deepeval FILE --out report.json`
  normalizes promptfoo results JSON, Inspect AI `.eval`/`.json` logs and DeepEval test-run
  JSON into a report (`eval.import` envelope) with an input-based suite digest, so `compare`
  can gate on results those tools produce. Fixtures generated with promptfoo 0.123.1,
  inspect_ai 0.3.270 and deepeval 4.2.6. New `inspect` extra (`zstandard`) for compressed
  `.eval` logs on Python < 3.14.
- `compare` refuses reports produced from different suites (exit 4) unless
  `--allow-suite-mismatch` is given.

### Changed
- **`compare` gates on the upper confidence bound of the regression**, not on the mean. A
  change can now fail when its mean regression is within budget but the interval is not.
  `--method mean` restores the pre-1.0 aggregate-mean check. A baseline case missing from the
  candidate counts as a failure.
- **`run --out` writes the envelope by default.** `--legacy-json` keeps the pre-1.0 format for
  one minor version.
- **`compare` exits 1 (not 4) when the regression is over budget**, so exit 1 always means
  "gate failed" and exit 4 always means an integrity failure.
- Relicensed from MIT to Apache-2.0. Releases before this change remain available under MIT.
  Added a `NOTICE` file.

### Fixed (behavior changes; review before upgrading)
- **Scoring no longer takes the best of several scorers.** A case passes only if every
  required scorer returns 1.0, and its score is the lowest required-scorer score. Before,
  `max(exact, json, plugins)` let a wrong answer with the right JSON keys score 1.0, and let a
  lenient plugin hide a failed exact match.
- Required scorers are now explicit: `json` when `scoring.json_schema` is set, plus every name
  in `scoring.scorers` (`exact` and `json` are built in). The default is `["exact"]`. Suites
  that set `json_schema` no longer also pass cases by exact match unless they list `exact`.
- `json_required_keys_score()` accepts an optional `expected=` keyword and compares values
  wherever the expected object has one. When `allow_extra_keys` is false, extra keys now lower
  the score instead of only setting `json_valid: false`. The positional signature is
  unchanged.
- **A missing prediction fails the case** (score 0.0, `missing_prediction: true`), including
  when `expected` is null. Before, a missing prediction against a null `expected` scored 1.0.
- An unknown scorer name, a prediction line without `id`, a duplicate prediction id, a case
  without `id` and a duplicate case id now raise `ValueError` (CLI exit 2). Before, unknown
  scorers were skipped, the last duplicate won, and a missing `id` raised `KeyError`.
- A plugin scorer that returns a value outside [0, 1] fails the case.
- **`run` now exits 1 when any case fails**, or when the suite has no cases. Before, it always
  exited 0. The report is still written.
- **`run` verifies packs before scoring**: the manifest always, and the Ed25519 signature when
  `--signature` is given or `<pack>.sig.json` sits next to the pack (`--public-key` required).
- `verify_pack()` rejects zip members that the manifest does not list, duplicate members, and
  manifests that omit `suite.json` or `cases.jsonl`. It returns `ok: false` for a file that is
  not a zip, where it used to raise.
- `load_suite_from_path()` verifies a pack and parses it in memory. It no longer extracts to a
  `.toolkit_eval_unpack_*` directory next to the zip, and raises `PackVerificationError` (a
  `ValueError`) when the manifest check fails.
- `extract_pack()` uses a real path-containment check. The old string-prefix check let members
  escape into sibling directories that share a name prefix.

### Added
- `run --signature` and `run --public-key`.
- `EXIT_CASES_FAILED = 1` in `toolkit_eval_harness.cli`.
- Report summary fields: `passed`, `failed`, `missing_predictions`, `unknown_predictions`,
  `scorers`. Case fields: `passed`, `missing_prediction`.
- `PackVerificationError`, `verify_pack_bytes()`, `load_suite_from_zip_bytes()` and
  `suite.parse_suite()`.
- Example suite (`examples/suite/`) and predictions (`examples/preds.jsonl`) used by the README
  quick start.

### Removed
- The unused `control_plane` package (tool specs and config adapter for an external
  orchestration framework) and its tests.
- `QUICKSTART.md`, `DEPLOYMENT.md` and `.env.example`. They described
  file formats, exit codes and environment variables that the code does not have. The README
  now holds the accurate usage guide.

### Earlier unreleased changes
- `--format` flag (`json`, `table`, `csv`) for all CLI commands.
- `--output` / `-o` flag to write results to a file instead of stdout.
- Plugin system for custom scorers via `register_scorer()` and entry points (`toolkit_eval_harness.scorers`).
- Pre-commit configuration with ruff and pyright hooks.
- Coverage threshold enforcement at 80% in CI.
- Comprehensive tests for all scorer types, compare budgets, pack/unpack round-trips, formatters, and plugins.
- CHANGELOG.md (this file).
- Expanded CONTRIBUTING.md with full development setup and plugin authoring guide.
- CI security scans are now blocking (removed `continue-on-error`).
- Improved error messages throughout CLI with contextual guidance on how to fix common issues.

## [0.1.0] - 2026-03-09

### Added
- Initial release.
- Core evaluation pipeline: create suite, pack, run, compare, report.
- Two built-in scorers: `exact_match` and `json_required_keys`.
- Ed25519 digital signatures for pack authenticity.
- SHA-256 hash verification for pack integrity.
- CLI with subcommands: `pack create/inspect/verify/sign/verify-signature`, `run`, `compare`, `validate-report`, `check-deps`, `keygen`.
- Structured JSON logging with `--log-format json`.
- Execution metadata in reports (timing, tool version, Python version).
- CI/CD pipeline with test matrix (Python 3.10/3.11/3.12), security scans, lint, build.
