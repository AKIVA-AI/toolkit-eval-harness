from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .compare import CompareBudget, compare_reports
from .io import read_bytes, read_json, read_text, write_json, write_text
from .pack import create_pack, load_suite_from_path, verify_pack
from .report import EvalReport, write_report_json
from .runner import run_suite
from .signing import generate_ed25519_keypair, sign_bytes, verify_bytes

logger = logging.getLogger(__name__)

EXIT_SUCCESS = 0
EXIT_CLI_ERROR = 2
EXIT_UNEXPECTED_ERROR = 3
EXIT_VALIDATION_FAILED = 4


def _cmd_pack_create(args: argparse.Namespace) -> int:
    """Create a suite pack zip from a suite directory."""
    suite_dir = Path(args.suite_dir).resolve()
    out = Path(args.out).resolve()
    
    logger.info(f"Creating pack from: {suite_dir}")
    
    try:
        create_pack(suite_dir=suite_dir, out_zip=out)
        print(str(out))
        logger.info(f"Pack created: {out}")
        return EXIT_SUCCESS
    except (ValueError, FileNotFoundError, PermissionError, OSError) as e:
        logger.error(f"Failed to create pack: {e}")
        return EXIT_CLI_ERROR


def _cmd_pack_inspect(args: argparse.Namespace) -> int:
    """Inspect a suite (dir or zip)."""
    suite_path = Path(args.suite).resolve()
    
    logger.info(f"Inspecting suite: {suite_path}")
    
    try:
        suite = load_suite_from_path(suite_path)
        payload = suite.to_dict()
        print(json.dumps(payload, indent=2, sort_keys=True))
        logger.info("Suite inspected successfully")
        return EXIT_SUCCESS
    except (ValueError, FileNotFoundError, PermissionError) as e:
        logger.error(f"Failed to inspect suite: {e}")
        return EXIT_CLI_ERROR


def _cmd_pack_verify(args: argparse.Namespace) -> int:
    """Verify pack integrity (hashes)."""
    pack_path = Path(args.suite).resolve()
    
    logger.info(f"Verifying pack: {pack_path}")
    
    try:
        res = verify_pack(pack_zip=pack_path)
        ok = bool(res.get("ok"))
        print(json.dumps(res, indent=2, sort_keys=True))
        
        if ok:
            logger.info("Pack verification passed")
            return EXIT_SUCCESS
        else:
            logger.warning("Pack verification failed")
            return EXIT_VALIDATION_FAILED
    except (ValueError, FileNotFoundError, PermissionError) as e:
        logger.error(f"Failed to verify pack: {e}")
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
    except (FileNotFoundError, PermissionError) as e:
        logger.error(f"Failed to read pack: {e}")
        return EXIT_CLI_ERROR
    
    try:
        private_pem = read_text(private_key_path)
        logger.debug("Private key loaded")
    except (FileNotFoundError, PermissionError) as e:
        logger.error(f"Failed to read private key: {e}")
        return EXIT_CLI_ERROR
    
    try:
        sig = sign_bytes(payload=payload, private_key_pem=private_pem)
        logger.info("Pack signed successfully")
    except Exception as e:
        logger.error(f"Failed to sign pack: {e}")
        return EXIT_CLI_ERROR
    
    sig_obj = {"algorithm": "ed25519", "signature_b64": sig}
    
    try:
        if args.out:
            write_json(Path(args.out), sig_obj)
        else:
            print(json.dumps(sig_obj, indent=2, sort_keys=True))
        return EXIT_SUCCESS
    except (OSError, PermissionError, ValueError) as e:
        logger.error(f"Failed to write signature: {e}")
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
    except (ValueError, FileNotFoundError, PermissionError) as e:
        logger.error(f"Failed to read signature: {e}")
        return EXIT_CLI_ERROR
    
    try:
        public_pem = read_text(public_key_path)
        logger.debug("Public key loaded")
    except (FileNotFoundError, PermissionError) as e:
        logger.error(f"Failed to read public key: {e}")
        return EXIT_CLI_ERROR
    
    try:
        payload = read_bytes(pack_path)
        ok = verify_bytes(payload=payload, signature_b64=sig_b64, public_key_pem=public_pem)
        
        if ok:
            logger.info("Signature verified successfully")
        else:
            logger.warning("Signature verification failed")
            
        print(json.dumps({"ok": ok}, indent=2, sort_keys=True))
        return EXIT_SUCCESS if ok else EXIT_VALIDATION_FAILED
    except (FileNotFoundError, PermissionError, Exception) as e:
        logger.error(f"Failed to verify signature: {e}")
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
    except (ValueError, FileNotFoundError, PermissionError) as e:
        logger.error(f"Failed to load suite: {e}")
        return EXIT_CLI_ERROR
    
    try:
        report = run_suite(suite=suite, predictions_path=predictions_path)
        logger.info("Suite run completed")
    except (ValueError, FileNotFoundError, PermissionError) as e:
        logger.error(f"Failed to run suite: {e}")
        return EXIT_CLI_ERROR
    
    if args.out:
        out = Path(args.out).resolve()
        try:
            write_report_json(report, out)
            logger.info(f"Wrote report to: {out}")
        except (OSError, PermissionError) as e:
            logger.error(f"Failed to write report: {e}")
            return EXIT_CLI_ERROR
    
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))
    return EXIT_SUCCESS


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
    except (ValueError, FileNotFoundError, PermissionError) as e:
        logger.error(f"Failed to read baseline: {e}")
        return EXIT_CLI_ERROR
    
    try:
        candidate_obj = read_json(candidate_path)
        candidate = EvalReport.from_dict(candidate_obj)
        logger.info("Loaded candidate report")
    except (ValueError, FileNotFoundError, PermissionError) as e:
        logger.error(f"Failed to read candidate: {e}")
        return EXIT_CLI_ERROR
    
    try:
        budget = CompareBudget(max_score_regression_pct=float(args.max_score_regression_pct))
        result = compare_reports(baseline=baseline, candidate=candidate, budget=budget)
        
        if result["passed"]:
            logger.info("Comparison passed")
        else:
            logger.warning("Comparison failed")
            
        print(json.dumps(result, indent=2, sort_keys=True))
        return EXIT_SUCCESS if result["passed"] else EXIT_VALIDATION_FAILED
    except Exception as e:
        logger.error(f"Failed to compare reports: {e}")
        return EXIT_CLI_ERROR


def _cmd_validate_report(args: argparse.Namespace) -> int:
    """Validate an eval report JSON has the expected shape."""
    report_path = Path(args.report).resolve()
    
    logger.info(f"Validating report: {report_path}")
    
    try:
        obj = read_json(report_path)
    except (ValueError, FileNotFoundError, PermissionError) as e:
        logger.error(f"Failed to read report: {e}")
        return EXIT_CLI_ERROR
    
    ok = (
        isinstance(obj, dict)
        and isinstance(obj.get("suite"), dict)
        and isinstance(obj.get("summary"), dict)
        and isinstance(obj.get("cases"), list)
    )
    
    if ok:
        logger.info("Report validation passed")
    else:
        logger.warning("Report validation failed")
    
    payload = {"ok": ok, "schema": "toolkit_eval_report", "schema_version": 1}
    print(json.dumps(payload, indent=2, sort_keys=True))
    return EXIT_SUCCESS if ok else EXIT_VALIDATION_FAILED


def build_parser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    p = argparse.ArgumentParser(
        prog="toolkit-eval",
        description="Toolkit Eval Harness - Run and compare evaluation suites",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging (DEBUG level)",
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
    
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stderr,
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


