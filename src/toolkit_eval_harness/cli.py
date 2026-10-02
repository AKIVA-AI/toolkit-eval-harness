from __future__ import annotations

import argparse
import json
import logging
import platform
import sys
import time
import zipfile
from pathlib import Path
from typing import Any

from . import __version__
from .compare import CompareBudget, compare_reports
from .envelope import (
    KIND_COMPARE,
    KIND_IMPORT,
    KIND_RUN,
    build_statement,
    file_resource,
    is_envelope,
    resource,
    validate_envelope,
    write_envelope,
)
from .formatters import get_formatter
from .importers import IMPORTERS
from .io import read_bytes, read_json, read_text, write_json, write_text
from .logging_config import setup_logging
from .pack import (
    PackVerificationError,
    create_pack,
    load_suite_from_path,
    load_suite_from_zip_bytes,
    verify_pack,
)
from .plugins import list_scorers
from .report import EvalReport
from .runner import run_suite
from .signing import generate_ed25519_keypair, sign_bytes, verify_bytes
from .suite import EvalSuite

logger = logging.getLogger(__name__)

# Exit codes (documented in README "Exit codes"). In a report envelope, 0 is verdict
# "pass", 1 is "fail" and every other code is "error".
EXIT_SUCCESS = 0  # command succeeded; for ``run``/``compare``, the gate passed
EXIT_CASES_FAILED = 1  # the gate failed: ``run`` had failing cases, ``compare`` regressed
EXIT_GATE_FAILED = EXIT_CASES_FAILED
EXIT_CLI_ERROR = 2  # bad arguments or unreadable/malformed input
EXIT_UNEXPECTED_ERROR = 3  # internal error or interrupt
EXIT_VALIDATION_FAILED = 4  # integrity failure: pack/signature check, invalid report

SIGNATURE_SUFFIX = ".sig.json"


def _emit(data: dict[str, Any], args: argparse.Namespace) -> None:
    """Format *data* according to ``--format`` and write to stdout or ``--output``."""
    fmt_name = getattr(args, "format", "json") or "json"
    output_path = getattr(args, "output", "") or ""

    formatter = get_formatter(fmt_name)
    text = formatter(data)

    if output_path:
        out = Path(output_path).resolve()
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
            logger.info("Wrote output to: %s", out)
        except (OSError, PermissionError) as e:
            logger.error(
                "Failed to write output to %s: %s. "
                "Check that the directory exists and you have write permission.",
                out,
                e,
            )
            raise
    else:
        print(text)


def _cmd_pack_create(args: argparse.Namespace) -> int:
    """Create a suite pack zip from a suite directory."""
    suite_dir = Path(args.suite_dir).resolve()
    out = Path(args.out).resolve()

    logger.info(f"Creating pack from: {suite_dir}")

    try:
        create_pack(suite_dir=suite_dir, out_zip=out)
        _emit({"created": str(out)}, args)
        logger.info(f"Pack created: {out}")
        return EXIT_SUCCESS
    except FileNotFoundError:
        logger.error(
            "Suite directory not found: %s. "
            "Ensure the directory exists and contains suite.json + cases.jsonl.",
            suite_dir,
        )
        return EXIT_CLI_ERROR
    except (ValueError, PermissionError, OSError) as e:
        logger.error("Failed to create pack: %s", e)
        return EXIT_CLI_ERROR


def _cmd_pack_inspect(args: argparse.Namespace) -> int:
    """Inspect a suite (dir or zip)."""
    suite_path = Path(args.suite).resolve()

    logger.info(f"Inspecting suite: {suite_path}")

    try:
        suite = load_suite_from_path(suite_path)
        payload = suite.to_dict()
        _emit(payload, args)
        logger.info("Suite inspected successfully")
        return EXIT_SUCCESS
    except PackVerificationError as e:
        logger.error("Pack failed verification: %s", e)
        return EXIT_VALIDATION_FAILED
    except FileNotFoundError:
        logger.error(
            "Suite not found at '%s'. "
            "Provide a path to a suite directory (containing suite.json + cases.jsonl) "
            "or a .zip pack file.",
            suite_path,
        )
        return EXIT_CLI_ERROR
    except (ValueError, PermissionError) as e:
        logger.error("Failed to inspect suite: %s", e)
        return EXIT_CLI_ERROR


def _cmd_pack_verify(args: argparse.Namespace) -> int:
    """Verify pack integrity (hashes)."""
    pack_path = Path(args.suite).resolve()

    logger.info(f"Verifying pack: {pack_path}")

    try:
        res = verify_pack(pack_zip=pack_path)
        ok = bool(res.get("ok"))
        _emit(res, args)

        if ok:
            logger.info("Pack verification passed")
            return EXIT_SUCCESS
        else:
            logger.warning(
                "Pack verification failed. The pack may have been modified after creation. "
                "Re-create the pack with 'pack create' to fix hash mismatches."
            )
            return EXIT_VALIDATION_FAILED
    except FileNotFoundError:
        logger.error(
            "Pack file not found: %s. Provide a path to a .zip pack file.",
            pack_path,
        )
        return EXIT_CLI_ERROR
    except (ValueError, PermissionError) as e:
        logger.error("Failed to verify pack: %s", e)
        return EXIT_CLI_ERROR


def _cmd_keygen(args: argparse.Namespace) -> int:
    """Generate Ed25519 keypair for signing."""
    private_key_path = Path(args.private_key).resolve()
    public_key_path = Path(args.public_key).resolve()

    logger.info("Generating Ed25519 keypair...")

    try:
        kp = generate_ed25519_keypair()
        logger.info("Keypair generated successfully")
    except Exception as e:
        logger.error(f"Failed to generate keypair: {e}")
        return EXIT_CLI_ERROR

    try:
        write_text(private_key_path, kp.private_key_pem)
        logger.info(f"Wrote private key to: {private_key_path}")

        write_text(public_key_path, kp.public_key_pem)
        logger.info(f"Wrote public key to: {public_key_path}")

        return EXIT_SUCCESS
    except (OSError, PermissionError) as e:
        logger.error(f"Failed to write key files: {e}")
        return EXIT_CLI_ERROR


def _cmd_pack_sign(args: argparse.Namespace) -> int:
    """Sign a pack zip (detached signature JSON)."""
    pack_path = Path(args.suite).resolve()
    private_key_path = Path(args.private_key).resolve()

    logger.info(f"Signing pack: {pack_path}")

    try:
        payload = read_bytes(pack_path)
        logger.debug("Pack loaded successfully")
    except FileNotFoundError:
        logger.error(
            "Pack file not found: %s. Provide a path to an existing .zip pack file.",
            pack_path,
        )
        return EXIT_CLI_ERROR
    except PermissionError as e:
        logger.error("Failed to read pack: %s", e)
        return EXIT_CLI_ERROR

    try:
        private_pem = read_text(private_key_path)
        logger.debug("Private key loaded")
    except FileNotFoundError:
        logger.error(
            "Private key not found: %s. Generate one with 'toolkit-eval keygen'.",
            private_key_path,
        )
        return EXIT_CLI_ERROR
    except PermissionError as e:
        logger.error("Failed to read private key: %s", e)
        return EXIT_CLI_ERROR

    try:
        sig = sign_bytes(payload=payload, private_key_pem=private_pem)
        logger.info("Pack signed successfully")
    except RuntimeError as e:
        logger.error(
            "Signing failed: %s. Install the 'cryptography' package: "
            "pip install 'toolkit-eval-harness[signing]'.",
            e,
        )
        return EXIT_CLI_ERROR
    except Exception as e:
        logger.error("Failed to sign pack: %s", e)
        return EXIT_CLI_ERROR

    sig_obj = {"algorithm": "ed25519", "signature_b64": sig}

    try:
        if args.out:
            write_json(Path(args.out), sig_obj)
        else:
            _emit(sig_obj, args)
        return EXIT_SUCCESS
    except (OSError, PermissionError, ValueError) as e:
        logger.error("Failed to write signature: %s", e)
        return EXIT_CLI_ERROR


def _cmd_pack_verify_sig(args: argparse.Namespace) -> int:
    """Verify a pack signature."""
    pack_path = Path(args.suite).resolve()
    signature_path = Path(args.signature).resolve()
    public_key_path = Path(args.public_key).resolve()

    logger.info(f"Verifying signature for: {pack_path}")

    try:
        sig_obj = read_json(signature_path)
        if not isinstance(sig_obj, dict):
            raise ValueError("Signature file must contain a JSON object")
        sig_b64 = str(sig_obj.get("signature_b64") or "")
    except FileNotFoundError:
        logger.error(
            "Signature file not found: %s. Create one with 'toolkit-eval pack sign'.",
            signature_path,
        )
        return EXIT_CLI_ERROR
    except (ValueError, PermissionError) as e:
        logger.error("Failed to read signature: %s", e)
        return EXIT_CLI_ERROR

    try:
        public_pem = read_text(public_key_path)
        logger.debug("Public key loaded")
    except FileNotFoundError:
        logger.error(
            "Public key not found: %s. Generate one with 'toolkit-eval keygen'.",
            public_key_path,
        )
        return EXIT_CLI_ERROR
    except PermissionError as e:
        logger.error("Failed to read public key: %s", e)
        return EXIT_CLI_ERROR

    try:
        payload = read_bytes(pack_path)
        ok = verify_bytes(payload=payload, signature_b64=sig_b64, public_key_pem=public_pem)

        if ok:
            logger.info("Signature verified successfully")
        else:
            logger.warning(
                "Signature verification failed. "
                "The pack may have been modified or signed with a different key."
            )

        _emit({"ok": ok}, args)
        return EXIT_SUCCESS if ok else EXIT_VALIDATION_FAILED
    except (FileNotFoundError, PermissionError, Exception) as e:
        logger.error("Failed to verify signature: %s", e)
        return EXIT_CLI_ERROR


def _cmd_run(args: argparse.Namespace) -> int:
    """Run an evaluation suite against predictions."""
    suite_path = Path(args.suite).resolve()
    predictions_path = Path(args.predictions).resolve()

    logger.info(f"Running suite: {suite_path}")
    logger.debug(f"Predictions: {predictions_path}")

    try:
        loaded = _load_suite_for_run(suite_path, args)
        if isinstance(loaded, int):
            if loaded == EXIT_VALIDATION_FAILED:
                _write_integrity_error_report(args, suite_path, "pack signature check failed")
            return loaded
        suite = loaded
        logger.info(f"Loaded suite: {suite.name}")
    except PackVerificationError as e:
        logger.error("Pack failed verification, refusing to run: %s", e)
        _write_integrity_error_report(args, suite_path, str(e))
        return EXIT_VALIDATION_FAILED
    except FileNotFoundError:
        logger.error(
            "Suite not found at '%s'. "
            "Provide a path to a suite directory (containing suite.json + cases.jsonl) "
            "or a .zip pack file.",
            suite_path,
        )
        return EXIT_CLI_ERROR
    except (ValueError, PermissionError) as e:
        logger.error("Failed to load suite: %s", e)
        return EXIT_CLI_ERROR

    start_time = time.monotonic()
    try:
        report = run_suite(
            suite=suite,
            predictions_path=predictions_path,
            allow_network_scorers=bool(getattr(args, "allow_network_scorers", False)),
        )
        logger.info("Suite run completed")
    except FileNotFoundError:
        logger.error(
            "Predictions file not found: %s. "
            'Provide a JSONL file with one {"id": ..., "prediction": ...} per line.',
            predictions_path,
        )
        return EXIT_CLI_ERROR
    except (ValueError, PermissionError) as e:
        logger.error("Failed to run suite: %s", e)
        return EXIT_CLI_ERROR
    elapsed = time.monotonic() - start_time

    # Enrich report with timing and metrics
    report_dict = report.to_dict()
    total_cases = int(report_dict["summary"].get("cases", 0))
    pass_count = sum(1 for c in report_dict.get("cases", []) if c.get("passed") is True)
    fail_count = total_cases - pass_count
    report_dict["summary"]["execution_time_seconds"] = round(elapsed, 4)
    report_dict["summary"]["pass_count"] = pass_count
    report_dict["summary"]["fail_count"] = fail_count
    report_dict["metadata"] = {
        "tool_version": __version__,
        "python_version": platform.python_version(),
        "platform": platform.platform(),
    }

    logger.info(
        f"Eval complete: {total_cases} cases, {pass_count} passed, "
        f"{fail_count} failed, {elapsed:.3f}s elapsed"
    )

    if total_cases == 0:
        logger.error("Suite has no cases; nothing was evaluated.")
        exit_code = EXIT_CASES_FAILED
    elif fail_count:
        logger.error("%d of %d case(s) failed.", fail_count, total_cases)
        exit_code = EXIT_CASES_FAILED
    else:
        exit_code = EXIT_SUCCESS

    if getattr(args, "out", "") and args.out:
        out = Path(args.out).resolve()
        try:
            if getattr(args, "legacy_json", False):
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_text(
                    json.dumps(report_dict, indent=2, sort_keys=True), encoding="utf-8"
                )
            else:
                statement = _run_statement(
                    args=args,
                    suite=suite,
                    suite_path=suite_path,
                    predictions_path=predictions_path,
                    report_dict=report_dict,
                    exit_code=exit_code,
                )
                write_envelope(out, statement)
            logger.info(f"Wrote report to: {out}")
        except (OSError, PermissionError, ValueError) as e:
            logger.error("Failed to write report to %s: %s", out, e)
            return EXIT_CLI_ERROR

    _emit(report_dict, args)
    return exit_code


def _run_statement(
    *,
    args: argparse.Namespace,
    suite: EvalSuite,
    suite_path: Path,
    predictions_path: Path,
    report_dict: dict[str, Any],
    exit_code: int,
) -> dict[str, Any]:
    """Build the ``eval.run`` report envelope."""
    summary = dict(report_dict["summary"])
    cases = int(summary.get("cases", 0))
    passed = int(summary.get("passed", 0))
    envelope_summary = {
        "cases": cases,
        "passed": passed,
        "failed": int(summary.get("failed", 0)),
        "pass_rate": (passed / cases) if cases else 0.0,
        "score": float(summary.get("score", 0.0)),
        "missing_predictions": int(summary.get("missing_predictions", 0)),
        "unknown_predictions": int(summary.get("unknown_predictions", 0)),
        "scorers": list(summary.get("scorers", [])),
    }
    suite_digest = suite.content_digest()
    if suite_path.is_file():
        suite_input = file_resource(suite_path, name=str(args.suite))
    else:
        suite_input = resource(str(args.suite), suite_digest)
    return build_statement(
        kind=KIND_RUN,
        subject=[resource(suite.name, suite_digest)],
        exit_code=exit_code,
        inputs=[suite_input, file_resource(predictions_path, name=str(args.predictions))],
        summary=envelope_summary,
        details={
            "suite": report_dict["suite"],
            "cases": report_dict["cases"],
            "environment": {
                "python_version": platform.python_version(),
                "platform": platform.platform(),
            },
            # Built-in scorer settings, including an LLM judge's model and prompt template.
            "scorer_config": summary.get("scorer_config", {}),
        },
        tool_version=__version__,
    )


def _write_integrity_error_report(
    args: argparse.Namespace, suite_path: Path, message: str
) -> None:
    """Write an ``error`` envelope for a pack that failed verification, if ``--out`` is set.

    The subject is the pack file itself, so the report records exactly which bytes failed.
    """
    out_arg = getattr(args, "out", "") or ""
    if not out_arg or getattr(args, "legacy_json", False) or not suite_path.is_file():
        return
    try:
        pack = file_resource(suite_path, name=str(args.suite))
        statement = build_statement(
            kind=KIND_RUN,
            subject=[pack],
            exit_code=EXIT_VALIDATION_FAILED,
            inputs=[pack],
            summary={},
            details={"error": "integrity_failure", "message": message},
            tool_version=__version__,
        )
        write_envelope(Path(out_arg).resolve(), statement)
    except (OSError, ValueError) as e:  # pragma: no cover - best effort
        logger.error("Failed to write error report: %s", e)


def _load_suite_for_run(suite_path: Path, args: argparse.Namespace) -> EvalSuite | int:
    """Load the suite for ``run``, verifying a pack before any case is scored.

    A pack is read into memory once. If a signature is supplied with ``--signature``, or
    a ``<pack>.sig.json`` file sits next to the pack, it is checked against
    ``--public-key`` over those same bytes; the manifest is then checked and the suite
    parsed from the same bytes. Returns an exit code instead of a suite on failure.
    """
    signature_arg = getattr(args, "signature", "") or ""
    public_key_arg = getattr(args, "public_key", "") or ""

    if suite_path.is_dir():
        if signature_arg or public_key_arg:
            logger.error(
                "--signature/--public-key apply to .zip packs only; %s is a directory.",
                suite_path,
            )
            return EXIT_CLI_ERROR
        return load_suite_from_path(suite_path)
    if suite_path.suffix.lower() != ".zip":
        return load_suite_from_path(suite_path)  # raises unsupported_suite_path

    data = read_bytes(suite_path)
    sibling = suite_path.with_name(suite_path.name + SIGNATURE_SUFFIX)
    signature_path: Path | None = None
    if signature_arg:
        signature_path = Path(signature_arg).resolve()
    elif sibling.is_file():
        signature_path = sibling
        logger.info("Found pack signature: %s", sibling)

    if signature_path is None:
        if public_key_arg:
            logger.error(
                "--public-key was given but no signature was found. Pass --signature or "
                "place the signature at %s.",
                sibling,
            )
            return EXIT_VALIDATION_FAILED
        logger.warning(
            "Pack is unsigned; only its internal manifest is checked, which does not "
            "detect deliberate tampering. Sign it with 'toolkit-eval pack sign'."
        )
    else:
        if not public_key_arg:
            logger.error(
                "Pack signature %s is present but no --public-key was given, so it "
                "cannot be checked. Refusing to run.",
                signature_path,
            )
            return EXIT_VALIDATION_FAILED
        sig_obj = read_json(signature_path)
        sig_b64 = str(sig_obj.get("signature_b64") or "") if isinstance(sig_obj, dict) else ""
        public_pem = read_text(Path(public_key_arg).resolve())
        try:
            ok = verify_bytes(payload=data, signature_b64=sig_b64, public_key_pem=public_pem)
        except RuntimeError as e:
            logger.error(
                "Cannot check the pack signature: %s. Install the 'cryptography' package "
                "(the [signing] extra).",
                e,
            )
            return EXIT_VALIDATION_FAILED
        if not ok:
            logger.error(
                "Pack signature does not match %s. The pack was modified or signed with "
                "a different key. Refusing to run.",
                suite_path,
            )
            return EXIT_VALIDATION_FAILED
        logger.info("Pack signature verified")

    return load_suite_from_zip_bytes(data)


def _cmd_import(args: argparse.Namespace) -> int:
    """Normalize promptfoo / Inspect AI / DeepEval results into a report."""
    source_path = Path(args.file).resolve()
    options: dict[str, Any] = {}
    if args.source == "promptfoo" and args.provider:
        options["provider"] = args.provider
    if args.source == "inspect" and args.scorer:
        options["scorer"] = args.scorer
    if args.source == "deepeval" and args.metric:
        options["metric"] = args.metric
    try:
        report = IMPORTERS[args.source](source_path, **options)
    except FileNotFoundError:
        logger.error("Results file not found: %s", source_path)
        return EXIT_CLI_ERROR
    except (ValueError, KeyError, TypeError, zipfile.BadZipFile) as e:
        logger.error("Failed to import %s results: %s", args.source, e)
        return EXIT_CLI_ERROR

    n = int(report.summary.get("cases", 0))
    failed = int(report.summary.get("failed", 0))
    exit_code = EXIT_CASES_FAILED if (n == 0 or failed) else EXIT_SUCCESS
    if n == 0:
        logger.error("No cases found in %s", source_path)
    elif failed:
        logger.warning("%d of %d imported case(s) failed.", failed, n)

    if args.out:
        statement = build_statement(
            kind=KIND_IMPORT,
            subject=[resource(str(report.suite.get("name")), str(report.suite["sha256"]))],
            exit_code=exit_code,
            inputs=[file_resource(source_path, name=str(args.file))],
            summary={**report.summary, "pass_rate": (report.summary["passed"] / n) if n else 0.0},
            details={"suite": report.suite, "cases": report.cases, "source": args.source},
            tool_version=__version__,
        )
        try:
            write_envelope(Path(args.out).resolve(), statement)
        except (OSError, ValueError) as e:
            logger.error("Failed to write report to %s: %s", args.out, e)
            return EXIT_CLI_ERROR

    _emit(report.to_dict(), args)
    return exit_code


def _cmd_check_deps(args: argparse.Namespace) -> int:
    """Check that required tools and dependencies are available."""
    results: dict[str, Any] = {"tool": "toolkit-eval", "version": __version__, "checks": []}
    all_ok = True

    # Check Python version
    py_ver = platform.python_version()
    py_ok = sys.version_info >= (3, 10)
    results["checks"].append({"name": "python>=3.10", "version": py_ver, "ok": py_ok})
    if not py_ok:
        all_ok = False

    # Check optional signing dependency
    try:
        import cryptography  # noqa: F401

        crypto_ver = cryptography.__version__  # type: ignore[attr-defined]
        results["checks"].append(
            {
                "name": "cryptography (signing)",
                "version": crypto_ver,
                "ok": True,
            }
        )
    except ImportError:
        results["checks"].append(
            {
                "name": "cryptography (signing)",
                "version": None,
                "ok": False,
                "note": "optional",
            }
        )

    # Report registered scorer plugins
    scorers = list_scorers()
    results["registered_scorers"] = scorers

    results["all_ok"] = all_ok
    _emit(results, args)
    return EXIT_SUCCESS if all_ok else EXIT_VALIDATION_FAILED


def _cmd_compare(args: argparse.Namespace) -> int:
    """Compare candidate report against baseline report."""
    baseline_path = Path(args.baseline).resolve()
    candidate_path = Path(args.candidate).resolve()

    logger.info("Comparing reports")
    logger.debug(f"Baseline: {baseline_path}")
    logger.debug(f"Candidate: {candidate_path}")

    try:
        baseline_obj = read_json(baseline_path)
        baseline = EvalReport.from_dict(baseline_obj)
        logger.info("Loaded baseline report")
    except FileNotFoundError:
        logger.error(
            "Baseline report not found: %s. "
            "Provide a path to a JSON report produced by 'toolkit-eval run'.",
            baseline_path,
        )
        return EXIT_CLI_ERROR
    except (ValueError, PermissionError) as e:
        logger.error("Failed to read baseline: %s", e)
        return EXIT_CLI_ERROR

    try:
        candidate_obj = read_json(candidate_path)
        candidate = EvalReport.from_dict(candidate_obj)
        logger.info("Loaded candidate report")
    except FileNotFoundError:
        logger.error(
            "Candidate report not found: %s. "
            "Provide a path to a JSON report produced by 'toolkit-eval run'.",
            candidate_path,
        )
        return EXIT_CLI_ERROR
    except (ValueError, PermissionError) as e:
        logger.error("Failed to read candidate: %s", e)
        return EXIT_CLI_ERROR

    try:
        max_new = getattr(args, "max_new_failures", None)
        budget = CompareBudget(
            max_score_regression_pct=float(args.max_score_regression_pct),
            method=str(getattr(args, "method", "bootstrap")),
            confidence=float(getattr(args, "confidence", 0.95)),
            iterations=int(getattr(args, "iterations", 10_000)),
            seed=int(getattr(args, "seed", 0)),
            max_new_failures=None if max_new is None else int(max_new),
            allow_suite_mismatch=bool(getattr(args, "allow_suite_mismatch", False)),
        )
        result = compare_reports(baseline=baseline, candidate=candidate, budget=budget)
    except Exception as e:
        logger.error("Failed to compare reports: %s", e)
        return EXIT_CLI_ERROR

    if result["passed"]:
        logger.info("Comparison passed")
        exit_code = EXIT_SUCCESS
    elif result.get("reason") == "suite_mismatch":
        logger.error(
            "Baseline and candidate were produced from different suites (%s vs %s). "
            "Refusing to compare; pass --allow-suite-mismatch to pair common case ids.",
            result.get("baseline_suite_sha256"),
            result.get("candidate_suite_sha256"),
        )
        exit_code = EXIT_VALIDATION_FAILED
    else:
        logger.warning(
            "Comparison FAILED (%s): regression %.2f%%, upper bound %.2f%% "
            "(max allowed: %.2f%%), %d new failure(s).",
            result.get("reason"),
            result.get("score_regression_pct") or 0.0,
            result.get("regression_pct_upper") or 0.0,
            budget.max_score_regression_pct,
            int(result.get("new_failure_count") or 0),
        )
        exit_code = EXIT_GATE_FAILED

    if getattr(args, "out", "") and args.out:
        statement = _compare_statement(
            args=args,
            baseline=baseline,
            candidate=candidate,
            baseline_path=baseline_path,
            candidate_path=candidate_path,
            result=result,
            exit_code=exit_code,
        )
        try:
            write_envelope(Path(args.out).resolve(), statement)
        except (OSError, ValueError) as e:
            logger.error("Failed to write report to %s: %s", args.out, e)
            return EXIT_CLI_ERROR

    _emit(result, args)
    return exit_code


COMPARE_SUMMARY_KEYS = (
    "reason",
    "method",
    "suite_check",
    "paired_cases",
    "baseline_score",
    "candidate_score",
    "mean_delta",
    "ci_low",
    "ci_high",
    "confidence",
    "score_regression_pct",
    "regression_pct_upper",
    "max_score_regression_pct",
    "new_failure_count",
    "fix_count",
    "max_new_failures",
)


def _compare_statement(
    *,
    args: argparse.Namespace,
    baseline: EvalReport,
    candidate: EvalReport,
    baseline_path: Path,
    candidate_path: Path,
    result: dict[str, Any],
    exit_code: int,
) -> dict[str, Any]:
    """Build the ``eval.compare`` report envelope.

    The subject is the suite both reports were produced from (its content digest) when both
    reports carry the same one; otherwise it is the candidate report file.
    """
    base_in = file_resource(baseline_path, name=str(args.baseline))
    cand_in = file_resource(candidate_path, name=str(args.candidate))
    suite_sha = str(candidate.suite.get("sha256") or "")
    if suite_sha and suite_sha == str(baseline.suite.get("sha256") or ""):
        subject = [resource(str(candidate.suite.get("name") or "suite"), suite_sha)]
    else:
        subject = [cand_in]
    summary_keys = COMPARE_SUMMARY_KEYS
    return build_statement(
        kind=KIND_COMPARE,
        subject=subject,
        exit_code=exit_code,
        inputs=[base_in, cand_in],
        summary={k: result.get(k) for k in summary_keys if k in result},
        details={k: v for k, v in result.items() if k not in summary_keys},
        tool_version=__version__,
    )


def _cmd_validate_report(args: argparse.Namespace) -> int:
    """Validate an eval report JSON has the expected shape."""
    report_path = Path(args.report).resolve()

    logger.info(f"Validating report: {report_path}")

    try:
        obj = read_json(report_path)
    except FileNotFoundError:
        logger.error(
            "Report file not found: %s. "
            "Provide a path to a JSON report produced by 'toolkit-eval run'.",
            report_path,
        )
        return EXIT_CLI_ERROR
    except (ValueError, PermissionError) as e:
        logger.error("Failed to read report: %s", e)
        return EXIT_CLI_ERROR

    errors: list[str] = []
    envelope = is_envelope(obj)
    if envelope:
        errors.extend(validate_envelope(obj))
        pred = obj.get("predicate")
        run_kinds = (KIND_RUN, KIND_IMPORT)
        if not errors and pred.get("kind") in run_kinds and pred.get("verdict") != "error":
            details = pred.get("details") or {}
            if not isinstance(details.get("suite"), dict):
                errors.append(f"{pred.get('kind')} details.suite must be an object.")
            if not isinstance(details.get("cases"), list):
                errors.append(f"{pred.get('kind')} details.cases must be an array.")
    elif not isinstance(obj, dict):
        errors.append("Root element must be a JSON object (dict).")
    else:
        if not isinstance(obj.get("suite"), dict):
            errors.append("Missing or invalid 'suite' key (expected object).")
        if not isinstance(obj.get("summary"), dict):
            errors.append("Missing or invalid 'summary' key (expected object).")
        if not isinstance(obj.get("cases"), list):
            errors.append("Missing or invalid 'cases' key (expected array).")

    ok = len(errors) == 0

    if ok:
        logger.info("Report validation passed")
    else:
        logger.warning(
            "Report validation failed: %s",
            "; ".join(errors),
        )

    payload: dict[str, Any] = {
        "ok": ok,
        "schema": "report-envelope" if envelope else "toolkit_eval_report",
        "schema_version": 1,
    }
    if errors:
        payload["errors"] = errors
    _emit(payload, args)
    return EXIT_SUCCESS if ok else EXIT_VALIDATION_FAILED


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    p = argparse.ArgumentParser(
        prog="toolkit-eval",
        description="Toolkit Eval Harness - Run and compare evaluation suites",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    verbosity = p.add_mutually_exclusive_group()
    verbosity.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging (DEBUG level)",
    )
    verbosity.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress all logging output (only errors to stderr)",
    )
    p.add_argument(
        "--log-format",
        choices=["text", "json"],
        default="text",
        help="Log output format (default: text)",
    )
    p.add_argument(
        "--log-file",
        default="",
        help="Write logs to FILE in addition to stderr",
        metavar="FILE",
    )
    p.add_argument(
        "--format",
        "-f",
        choices=["json", "table", "csv", "markdown"],
        default="json",
        help="Output data format (default: json)",
    )
    p.add_argument(
        "--output",
        "-o",
        default="",
        help="Write output to FILE instead of stdout",
        metavar="FILE",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    keygen = sub.add_parser("keygen", help="Generate an Ed25519 keypair for signing suite packs.")
    keygen.add_argument("--private-key", required=True, help="Output private key file path")
    keygen.add_argument("--public-key", required=True, help="Output public key file path")
    keygen.set_defaults(func=_cmd_keygen)

    pack = sub.add_parser("pack", help="Suite pack utilities (zip).")
    pack_sub = pack.add_subparsers(dest="pack_cmd", required=True)

    pack_create = pack_sub.add_parser(
        "create", help="Create a suite pack zip from a suite directory."
    )
    pack_create.add_argument("--suite-dir", required=True, help="Suite directory path")
    pack_create.add_argument("--out", required=True, help="Output pack zip file path")
    pack_create.set_defaults(func=_cmd_pack_create)

    pack_inspect = pack_sub.add_parser("inspect", help="Inspect a suite (dir or zip).")
    pack_inspect.add_argument("--suite", required=True, help="Suite path (directory or zip)")
    pack_inspect.set_defaults(func=_cmd_pack_inspect)

    pack_verify = pack_sub.add_parser("verify", help="Verify pack integrity (hashes).")
    pack_verify.add_argument("--suite", required=True, help="Pack zip file path")
    pack_verify.set_defaults(func=_cmd_pack_verify)

    pack_sign = pack_sub.add_parser("sign", help="Sign a pack zip (detached signature JSON).")
    pack_sign.add_argument("--suite", required=True, help="Pack zip file path")
    pack_sign.add_argument("--private-key", required=True, help="Private key PEM file path")
    pack_sign.add_argument("--out", default="", help="Output signature file (default: stdout)")
    pack_sign.set_defaults(func=_cmd_pack_sign)

    pack_verify_sig = pack_sub.add_parser("verify-signature", help="Verify a pack signature.")
    pack_verify_sig.add_argument("--suite", required=True, help="Pack zip file path")
    pack_verify_sig.add_argument("--signature", required=True, help="Signature JSON file path")
    pack_verify_sig.add_argument("--public-key", required=True, help="Public key PEM file path")
    pack_verify_sig.set_defaults(func=_cmd_pack_verify_sig)

    run = sub.add_parser("run", help="Run an evaluation suite against predictions.")
    run.add_argument("--suite", required=True, help="Suite path (directory or zip)")
    run.add_argument("--predictions", required=True, help="Predictions JSONL (id+prediction)")
    run.add_argument(
        "--out",
        default="",
        help="Write the report envelope (canonical JSON, in-toto Statement v1) to this path",
    )
    run.add_argument(
        "--legacy-json",
        action="store_true",
        help="With --out, write the pre-1.0 report JSON instead of the envelope (deprecated)",
    )
    run.add_argument(
        "--signature",
        default="",
        help=(
            "Detached pack signature JSON to verify before running (default: "
            f"<pack>{SIGNATURE_SUFFIX} next to the pack, if present)"
        ),
    )
    run.add_argument(
        "--public-key", default="", help="Public key PEM used to verify the pack signature"
    )
    run.add_argument(
        "--allow-network-scorers",
        action="store_true",
        help="Allow the embedding and llm_judge scorers, which call a model over the network "
        "(off by default)",
    )
    run.set_defaults(func=_cmd_run)

    compare = sub.add_parser("compare", help="Compare candidate report against baseline report.")
    compare.add_argument("--baseline", required=True, help="Baseline report JSON file path")
    compare.add_argument("--candidate", required=True, help="Candidate report JSON file path")
    compare.add_argument(
        "--max-score-regression-pct",
        default="2.0",
        help="Max score regression %% (default: 2.0)",
    )
    compare.add_argument(
        "--method",
        choices=["bootstrap", "mean"],
        default="bootstrap",
        help="bootstrap: gate on the CI upper bound of the regression (default); "
        "mean: pre-1.0 aggregate-mean comparison",
    )
    compare.add_argument(
        "--confidence", type=float, default=0.95, help="Confidence level (default: 0.95)"
    )
    compare.add_argument(
        "--iterations", type=int, default=10_000, help="Bootstrap resamples (default: 10000)"
    )
    compare.add_argument("--seed", type=int, default=0, help="Bootstrap RNG seed (default: 0)")
    compare.add_argument(
        "--max-new-failures",
        type=int,
        default=None,
        help="Also fail when more than N cases flip from pass to fail (default: not gated)",
    )
    compare.add_argument(
        "--allow-suite-mismatch",
        action="store_true",
        help="Compare reports from different suites, pairing only common case ids",
    )
    compare.add_argument(
        "--out",
        default="",
        help="Write the comparison envelope (canonical JSON, in-toto Statement v1) to this path",
    )
    compare.set_defaults(func=_cmd_compare)

    imp = sub.add_parser(
        "import",
        help="Normalize promptfoo, Inspect AI or DeepEval results into a report.",
    )
    imp.add_argument("source", choices=list(IMPORTERS), help="Tool that produced the file")
    imp.add_argument(
        "file",
        help="promptfoo results.json, Inspect .eval/.json log, or DeepEval test-run JSON",
    )
    imp.add_argument(
        "--out",
        default="",
        help="Write the report envelope (kind eval.import) to this path",
    )
    imp.add_argument("--provider", default="", help="promptfoo: keep only this provider")
    imp.add_argument("--scorer", default="", help="Inspect: use only this scorer")
    imp.add_argument("--metric", default="", help="DeepEval: use only this metric")
    imp.set_defaults(func=_cmd_import)

    validate_report = sub.add_parser(
        "validate-report", help="Validate an eval report JSON has the expected shape."
    )
    validate_report.add_argument(
        "--report", required=True, help="Report JSON file path to validate"
    )
    validate_report.set_defaults(func=_cmd_validate_report)

    check_deps = sub.add_parser(
        "check-deps", help="Verify all required tools and dependencies are available."
    )
    check_deps.set_defaults(func=_cmd_check_deps)

    return p


def main(argv: list[str] | None = None) -> int:
    """Main entry point for CLI.

    Args:
        argv: Command line arguments (defaults to sys.argv)

    Returns:
        Exit code (0 = success, non-zero = error)
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.quiet:
        level = logging.ERROR
    elif args.verbose:
        level = logging.DEBUG
    else:
        level = logging.WARNING

    setup_logging(
        level=level,
        fmt=args.log_format,
        log_file=getattr(args, "log_file", "") or "",
    )

    try:
        return int(args.func(args))
    except (ValueError, FileNotFoundError, PermissionError) as e:
        logger.error(f"{type(e).__name__}: {e}")
        return EXIT_CLI_ERROR
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        return EXIT_UNEXPECTED_ERROR
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(
            "\nAn unexpected error occurred. Please report this issue.",
            file=sys.stderr,
        )
        return EXIT_UNEXPECTED_ERROR
