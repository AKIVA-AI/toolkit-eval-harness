from __future__ import annotations

import argparse
import json
import logging
import platform
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__
from .compare import CompareBudget, compare_reports
from .formatters import get_formatter
from .io import read_bytes, read_json, read_text, write_json, write_text
from .logging_config import setup_logging
from .pack import create_pack, load_suite_from_path, verify_pack
from .plugins import list_scorers
from .report import EvalReport
from .runner import run_suite
from .signing import generate_ed25519_keypair, sign_bytes, verify_bytes

logger = logging.getLogger(__name__)

EXIT_SUCCESS = 0
EXIT_CLI_ERROR = 2
EXIT_UNEXPECTED_ERROR = 3
EXIT_VALIDATION_FAILED = 4


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
            "Signature file not found: %s. "
            "Create one with 'toolkit-eval pack sign'.",
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
        suite = load_suite_from_path(suite_path)
        logger.info(f"Loaded suite: {suite.name}")
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
        report = run_suite(suite=suite, predictions_path=predictions_path)
        logger.info("Suite run completed")
    except FileNotFoundError:
        logger.error(
            "Predictions file not found: %s. "
            "Provide a JSONL file with one {\"id\": ..., \"prediction\": ...} per line.",
            predictions_path,
        )
        return EXIT_CLI_ERROR
    except (ValueError, PermissionError) as e:
        logger.error("Failed to run suite: %s", e)
        return EXIT_CLI_ERROR
    elapsed = time.monotonic() - start_time

    # Enrich report with timing and metrics
    report_dict = report.to_dict()
    total_cases = report_dict["summary"].get("cases", 0)
    pass_count = sum(1 for c in report_dict.get("cases", []) if c.get("score", 0) >= 1.0)
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

    # Legacy --out flag (kept for backward compat)
    if getattr(args, "out", "") and args.out:
        out = Path(args.out).resolve()
        try:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(
                json.dumps(report_dict, indent=2, sort_keys=True), encoding="utf-8"
            )
            logger.info(f"Wrote report to: {out}")
        except (OSError, PermissionError) as e:
            logger.error("Failed to write report to %s: %s", out, e)
            return EXIT_CLI_ERROR

    _emit(report_dict, args)
    return EXIT_SUCCESS


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
        results["checks"].append({
            "name": "cryptography (signing)", "version": crypto_ver, "ok": True,
        })
    except ImportError:
        results["checks"].append({
            "name": "cryptography (signing)", "version": None,
            "ok": False, "note": "optional",
        })

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
        budget = CompareBudget(max_score_regression_pct=float(args.max_score_regression_pct))
        result = compare_reports(baseline=baseline, candidate=candidate, budget=budget)

        if result["passed"]:
            logger.info("Comparison passed")
        else:
            logger.warning(
                "Comparison FAILED: score regressed %.2f%% (max allowed: %.2f%%).",
                result.get("score_regression_pct", 0),
                budget.max_score_regression_pct,
            )

        _emit(result, args)
        return EXIT_SUCCESS if result["passed"] else EXIT_VALIDATION_FAILED
    except Exception as e:
        logger.error("Failed to compare reports: %s", e)
        return EXIT_CLI_ERROR


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
    if not isinstance(obj, dict):
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
        "schema": "toolkit_eval_report",
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
        "--format",
        "-f",
        choices=["json", "table", "csv"],
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
    run.add_argument("--out", default="", help="Optional output report JSON path")
    run.set_defaults(func=_cmd_run)

    compare = sub.add_parser("compare", help="Compare candidate report against baseline report.")
    compare.add_argument("--baseline", required=True, help="Baseline report JSON file path")
    compare.add_argument("--candidate", required=True, help="Candidate report JSON file path")
    compare.add_argument(
        "--max-score-regression-pct",
        default="2.0",
        help="Max score regression %% (default: 2.0)",
    )
    compare.set_defaults(func=_cmd_compare)

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


