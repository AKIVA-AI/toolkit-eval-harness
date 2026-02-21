from __future__ import annotations

import json
from pathlib import Path

from toolkit_eval_harness.pack import create_pack, load_suite_from_path


def test_load_suite_from_zip_twice_cleans_unpack_dir(tmp_path: Path) -> None:
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "suite.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "name": "demo",
                "description": "",
                "created_at": "2025-12-14T00:00:00Z",
                "scoring": {},
            }
        ),
        encoding="utf-8",
    )
    (suite_dir / "cases.jsonl").write_text(
        json.dumps({"id": "c1", "input": {"prompt": "x"}, "expected": "y"}) + "\n",
        encoding="utf-8",
    )

    pack = tmp_path / "suite.zip"
    create_pack(suite_dir=suite_dir, out_zip=pack)

    a = load_suite_from_path(pack)
    b = load_suite_from_path(pack)
    assert a.name == "demo"
    assert b.name == "demo"

