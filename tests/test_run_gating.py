"""`run` gating: exit codes, pack verification before execution, and pack integrity."""

from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from toolkit_eval_harness.cli import (
    EXIT_CASES_FAILED,
    EXIT_SUCCESS,
    EXIT_VALIDATION_FAILED,
    main,
)
from toolkit_eval_harness.pack import (
    PackVerificationError,
    create_pack,
    extract_pack,
    load_suite_from_path,
    verify_pack,
)


def _suite_dir(tmp_path: Path) -> Path:
    suite_dir = tmp_path / "suite"
    suite_dir.mkdir()
    (suite_dir / "suite.json").write_text(
        json.dumps({"schema_version": 1, "name": "gate", "scoring": {}}), encoding="utf-8"
    )
    (suite_dir / "cases.jsonl").write_text(
        json.dumps({"id": "c1", "expected": "yes"})
        + "\n"
        + json.dumps({"id": "c2", "expected": "no"})
        + "\n",
        encoding="utf-8",
    )
    return suite_dir


def _preds(tmp_path: Path, c2: str) -> Path:
    p = tmp_path / "preds.jsonl"
    p.write_text(
        json.dumps({"id": "c1", "prediction": "yes"})
        + "\n"
        + json.dumps({"id": "c2", "prediction": c2})
        + "\n",
        encoding="utf-8",
    )
    return p


def _rewrite_pack(src: Path, dst: Path, cases: bytes, *, fix_manifest: bool) -> None:
    """Copy *src* to *dst*, replacing cases.jsonl and optionally re-hashing the manifest."""
    with zipfile.ZipFile(src) as zin:
        members = {n: zin.read(n) for n in zin.namelist()}
    members["cases.jsonl"] = cases
    if fix_manifest:
        manifest = json.loads(members["manifest.json"])
        manifest["files"]["cases.jsonl"] = {
            "sha256": hashlib.sha256(cases).hexdigest(),
            "size": len(cases),
        }
        members["manifest.json"] = json.dumps(manifest).encode("utf-8")
    with zipfile.ZipFile(dst, "w") as zout:
        for name, data in members.items():
            zout.writestr(name, data)


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------


class TestRunExitCodes:
    def test_all_cases_pass_exits_zero(self, tmp_path: Path) -> None:
        rc = main(["run", "--suite", str(_suite_dir(tmp_path)), "--predictions",
                   str(_preds(tmp_path, "no"))])
        assert rc == EXIT_SUCCESS

    def test_failed_case_exits_nonzero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = main(["run", "--suite", str(_suite_dir(tmp_path)), "--predictions",
                   str(_preds(tmp_path, "WRONG"))])
        assert rc == EXIT_CASES_FAILED
        report = json.loads(capsys.readouterr().out)
        assert report["summary"]["pass_count"] == 1
        assert report["summary"]["fail_count"] == 1

    def test_missing_prediction_exits_nonzero(self, tmp_path: Path) -> None:
        preds = tmp_path / "preds.jsonl"
        preds.write_text(json.dumps({"id": "c1", "prediction": "yes"}) + "\n", encoding="utf-8")
        rc = main(["run", "--suite", str(_suite_dir(tmp_path)), "--predictions", str(preds)])
        assert rc == EXIT_CASES_FAILED

    def test_prediction_line_without_id_is_a_cli_error(self, tmp_path: Path) -> None:
        preds = tmp_path / "preds.jsonl"
        preds.write_text(json.dumps({"prediction": "yes"}) + "\n", encoding="utf-8")
        rc = main(["run", "--suite", str(_suite_dir(tmp_path)), "--predictions", str(preds)])
        assert rc == 2


# ---------------------------------------------------------------------------
# Pack verification
# ---------------------------------------------------------------------------


class TestPackIntegrity:
    def test_extra_member_fails_verification(self, tmp_path: Path) -> None:
        pack = tmp_path / "suite.zip"
        create_pack(suite_dir=_suite_dir(tmp_path), out_zip=pack)
        with zipfile.ZipFile(pack, "a") as zf:
            zf.writestr("evil.txt", "x")
        res = verify_pack(pack_zip=pack)
        assert res["ok"] is False
        assert {"file": "evil.txt", "reason": "not_in_manifest"} in res["failures"]

    def test_manifest_must_cover_suite_files(self, tmp_path: Path) -> None:
        pack = tmp_path / "suite.zip"
        with zipfile.ZipFile(pack, "w") as zf:
            zf.writestr("manifest.json", json.dumps({"files": {}}))
            zf.writestr("suite.json", "{}")
            zf.writestr("cases.jsonl", "")
        res = verify_pack(pack_zip=pack)
        assert res["ok"] is False

    def test_hash_mismatch_blocks_loading(self, tmp_path: Path) -> None:
        good = tmp_path / "good.zip"
        create_pack(suite_dir=_suite_dir(tmp_path), out_zip=good)
        bad = tmp_path / "bad.zip"
        _rewrite_pack(good, bad, b'{"id": "c1", "expected": "hacked"}\n', fix_manifest=False)
        with pytest.raises(PackVerificationError):
            load_suite_from_path(bad)

    def test_loading_a_pack_writes_nothing_beside_it(self, tmp_path: Path) -> None:
        packs = tmp_path / "packs"
        packs.mkdir()
        pack = packs / "suite.zip"
        create_pack(suite_dir=_suite_dir(tmp_path), out_zip=pack)
        suite = load_suite_from_path(pack)
        assert [c.id for c in suite.cases] == ["c1", "c2"]
        assert sorted(p.name for p in packs.iterdir()) == ["suite.zip"]

    def test_zip_slip_into_sibling_prefix_dir_is_blocked(self, tmp_path: Path) -> None:
        pack = tmp_path / "evil.zip"
        with zipfile.ZipFile(pack, "w") as zf:
            zf.writestr("../out2/x.txt", "x")
        with pytest.raises(ValueError, match="zip_path_traversal_blocked"):
            extract_pack(pack_zip=pack, dest_dir=tmp_path / "out")
        assert not (tmp_path / "out2").exists()

    def test_run_refuses_a_tampered_pack(self, tmp_path: Path) -> None:
        good = tmp_path / "good.zip"
        create_pack(suite_dir=_suite_dir(tmp_path), out_zip=good)
        bad = tmp_path / "bad.zip"
        _rewrite_pack(good, bad, b'{"id": "c1", "expected": "yes"}\n', fix_manifest=False)
        rc = main(["run", "--suite", str(bad), "--predictions", str(_preds(tmp_path, "no"))])
        assert rc == EXIT_VALIDATION_FAILED


class TestRunSignature:
    @pytest.fixture()
    def keys(self, tmp_path: Path) -> tuple[Path, Path]:
        pytest.importorskip("cryptography")
        priv, pub = tmp_path / "priv.pem", tmp_path / "pub.pem"
        assert main(["keygen", "--private-key", str(priv), "--public-key", str(pub)]) == 0
        return priv, pub

    def _signed_pack(self, tmp_path: Path, priv: Path) -> tuple[Path, Path]:
        pack = tmp_path / "suite.zip"
        create_pack(suite_dir=_suite_dir(tmp_path), out_zip=pack)
        sig = tmp_path / "suite.zip.sig.json"
        assert main(["pack", "sign", "--suite", str(pack), "--private-key", str(priv),
                     "--out", str(sig)]) == 0
        return pack, sig

    def test_valid_signature_runs(self, tmp_path: Path, keys: tuple[Path, Path]) -> None:
        priv, pub = keys
        pack, sig = self._signed_pack(tmp_path, priv)
        rc = main(["run", "--suite", str(pack), "--signature", str(sig), "--public-key",
                   str(pub), "--predictions", str(_preds(tmp_path, "no"))])
        assert rc == EXIT_SUCCESS

    def test_tampered_cases_with_updated_manifest_fails(
        self, tmp_path: Path, keys: tuple[Path, Path]
    ) -> None:
        priv, pub = keys
        pack, sig = self._signed_pack(tmp_path, priv)
        forged = tmp_path / "forged.zip"
        _rewrite_pack(
            pack,
            forged,
            b'{"id": "c1", "expected": "yes"}\n{"id": "c2", "expected": "WRONG"}\n',
            fix_manifest=True,
        )
        # The forged pack is internally consistent, so hash checks alone cannot catch it...
        assert verify_pack(pack_zip=forged)["ok"] is True
        # ...but the signature over the original pack bytes does.
        rc = main(["run", "--suite", str(forged), "--signature", str(sig), "--public-key",
                   str(pub), "--predictions", str(_preds(tmp_path, "WRONG"))])
        assert rc == EXIT_VALIDATION_FAILED

    def test_sibling_signature_is_enforced(self, tmp_path: Path, keys: tuple[Path, Path]) -> None:
        priv, pub = keys
        pack, _sig = self._signed_pack(tmp_path, priv)
        # A <pack>.sig.json next to the pack is picked up automatically; without a public
        # key it cannot be checked, so the run must refuse rather than ignore it.
        rc = main(["run", "--suite", str(pack), "--predictions", str(_preds(tmp_path, "no"))])
        assert rc == EXIT_VALIDATION_FAILED
        rc = main(["run", "--suite", str(pack), "--public-key", str(pub), "--predictions",
                   str(_preds(tmp_path, "no"))])
        assert rc == EXIT_SUCCESS

    def test_signature_flag_requires_public_key(
        self, tmp_path: Path, keys: tuple[Path, Path]
    ) -> None:
        priv, _pub = keys
        pack, sig = self._signed_pack(tmp_path, priv)
        rc = main(["run", "--suite", str(pack), "--signature", str(sig), "--predictions",
                   str(_preds(tmp_path, "no"))])
        assert rc == EXIT_VALIDATION_FAILED
