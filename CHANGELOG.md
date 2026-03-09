# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `--format` flag (`json`, `table`, `csv`) for all CLI commands.
- `--output` / `-o` flag to write results to a file instead of stdout.
- Plugin system for custom scorers via `register_scorer()` and entry points (`toolkit_eval_harness.scorers`).
- Pre-commit configuration with ruff and pyright hooks.
- Coverage threshold enforcement at 70% in CI.
- Comprehensive tests for all scorer types, compare budgets, pack/unpack round-trips, formatters, and plugins.
- CHANGELOG.md (this file).
- Expanded CONTRIBUTING.md with full development setup and plugin authoring guide.

### Changed
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
