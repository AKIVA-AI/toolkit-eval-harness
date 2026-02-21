from __future__ import annotations

import json
from pathlib import Path

import pytest

from toolkit_eval_harness.cli import build_parser


def test_cli_version_flag_prints(capsys: pytest.CaptureFixture[str]) -> None:
    parser = build_parser()
    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["--version"])
    assert exc.value.code == 0
    assert "toolkit-eval" in capsys.readouterr().out


def test_cli_pack_inspect_and_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "suite.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "demo",
                "description": "demo suite",
                "created_at": "2025-12-14T00:00:00Z",
                "scoring": {"json_schema": {"required_keys": ["status"]}},
            }
        ),
        encoding="utf-8",
    )
    (suite_dir / "cases.jsonl").write_text(
        json.dumps({"id": "c1", "input": {"prompt": "x"}, "expected": {"status": "ok"}}) + "\n",
        encoding="utf-8",
    )

    preds = tmp_path / "preds.jsonl"
    preds.write_text(
        json.dumps({"id": "c1", "prediction": json.dumps({"status": "ok"})}) + "\n",
        encoding="utf-8",
    )

    parser = build_parser()

    # Pack create + verify hashes
    out_zip = tmp_path / "suite.zip"
    create_args = parser.parse_args(
        ["pack", "create", "--suite-dir", str(suite_dir), "--out", str(out_zip)]
    )
    assert int(create_args.func(create_args)) == 0
    verify_args = parser.parse_args(["pack", "verify", "--suite", str(out_zip)])
    assert int(verify_args.func(verify_args)) == 0
    capsys.readouterr()

    # Optional signature path (runs only if deps present)
    try:
        import cryptography  # noqa: F401
    except Exception:
        pass
    else:
        priv = tmp_path / "priv.pem"
        pub = tmp_path / "pub.pem"
        keygen_args = parser.parse_args(
            ["keygen", "--private-key", str(priv), "--public-key", str(pub)]
        )
        assert int(keygen_args.func(keygen_args)) == 0
        sig = tmp_path / "suite.sig.json"
        sign_args = parser.parse_args(
            ["pack", "sign", "--suite", str(out_zip), "--private-key", str(priv), "--out", str(sig)]
        )
        assert int(sign_args.func(sign_args)) == 0
        verify_sig_args = parser.parse_args(
            [
                "pack",
                "verify-signature",
                "--suite",
                str(out_zip),
                "--signature",
                str(sig),
                "--public-key",
                str(pub),
            ]
        )
        assert int(verify_sig_args.func(verify_sig_args)) == 0

    capsys.readouterr()

    inspect_args = parser.parse_args(["pack", "inspect", "--suite", str(suite_dir)])
    assert int(inspect_args.func(inspect_args)) == 0
    inspected = json.loads(capsys.readouterr().out)
    assert inspected["name"] == "demo"

    out_report = tmp_path / "report.json"
    run_args = parser.parse_args(
        ["run", "--suite", str(suite_dir), "--predictions", str(preds), "--out", str(out_report)]
    )
    assert int(run_args.func(run_args)) == 0
    assert out_report.exists()
    validate_args = parser.parse_args(["validate-report", "--report", str(out_report)])
    assert int(validate_args.func(validate_args)) == 0


def test_cli_compare_exit_code(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    baseline = tmp_path / "baseline.json"
    candidate = tmp_path / "candidate.json"
    baseline.write_text(
        json.dumps({"suite": {}, "summary": {"score": 1.0}, "cases": []}),
        encoding="utf-8",
    )
    candidate.write_text(
        json.dumps({"suite": {}, "summary": {"score": 0.5}, "cases": []}),
        encoding="utf-8",
    )

    parser = build_parser()
    args = parser.parse_args(
        [
            "compare",
            "--baseline",
            str(baseline),
            "--candidate",
            str(candidate),
            "--max-score-regression-pct",
            "2.0",
        ]
    )
    rc = int(args.func(args))
    assert rc == 4
    payload = json.loads(capsys.readouterr().out)
    assert payload["passed"] is False

