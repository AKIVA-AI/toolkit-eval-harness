from __future__ import annotations

import json
from pathlib import Path

from toolkit_eval_harness.pack import create_pack, load_suite_from_path
from toolkit_eval_harness.runner import run_suite


def test_pack_create_and_run(tmp_path: Path) -> None:
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "suite.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "demo",
                "description": "demo suite",
                "created_at": "2025-12-14T00:00:00Z",
                "scoring": {"json_schema": {"required_keys": ["status", "result"]}},
            }
        ),
        encoding="utf-8",
    )
    (suite_dir / "cases.jsonl").write_text(
        "\n".join(
            [
                json.dumps({"id": "c1", "input": {"prompt": "x"}, "expected": {"status": "ok"}}),
                json.dumps({"id": "c2", "input": {"prompt": "y"}, "expected": "hello"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    pack = tmp_path / "suite.zip"
    create_pack(suite_dir=suite_dir, out_zip=pack)
    suite = load_suite_from_path(pack)

    preds = tmp_path / "preds.jsonl"
    preds.write_text(
        "\n".join(
            [
                json.dumps({"id": "c1", "prediction": json.dumps({"status": "ok", "result": {}})}),
                json.dumps({"id": "c2", "prediction": "hello"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    report = run_suite(suite=suite, predictions_path=preds)
    assert report.summary["cases"] == 2
    assert 0.9 <= float(report.summary["score"]) <= 1.0

