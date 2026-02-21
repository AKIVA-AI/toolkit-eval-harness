from __future__ import annotations

import json
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .hashing import sha256_file
from .suite import EvalSuite, read_suite_dir


@dataclass(frozen=True)
class SuitePack:
    schema_version: int
    name: str


def _manifest_for_suite_dir(suite_dir: Path) -> dict[str, object]:
    suite_path = suite_dir / "suite.json"
    cases_path = suite_dir / "cases.jsonl"
    return {
        "version": 1,
        "created_ts": float(time.time()),
        "files": {
            "suite.json": {
                "sha256": sha256_file(suite_path),
                "size": int(suite_path.stat().st_size),
            },
            "cases.jsonl": {
                "sha256": sha256_file(cases_path),
                "size": int(cases_path.stat().st_size),
            },
        },
    }


def create_pack(*, suite_dir: Path, out_zip: Path) -> None:
    suite = read_suite_dir(suite_dir)
    meta = SuitePack(schema_version=1, name=suite.name)
    manifest = _manifest_for_suite_dir(suite_dir)

    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("pack.json", json.dumps(meta.__dict__, indent=2, sort_keys=True))
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        zf.write(suite_dir / "suite.json", arcname="suite.json")
        zf.write(suite_dir / "cases.jsonl", arcname="cases.jsonl")


def verify_pack(*, pack_zip: Path) -> dict[str, object]:
    """
    Verifies hashes against manifest.json in the pack.
    """
    with zipfile.ZipFile(pack_zip, "r") as zf:
        names = set(zf.namelist())
        if "manifest.json" not in names:
            return {"ok": False, "reason": "missing_manifest"}
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        files = manifest.get("files") if isinstance(manifest, dict) else None
        if not isinstance(files, dict):
            return {"ok": False, "reason": "invalid_manifest"}
        failures: list[dict[str, str]] = []
        for fname, meta in files.items():
            if fname not in names:
                failures.append({"file": str(fname), "reason": "missing"})
                continue
            expected = ""
            if isinstance(meta, dict):
                expected = str(meta.get("sha256") or "")
            content = zf.read(fname)
            import hashlib

            got = hashlib.sha256(content).hexdigest()
            if got != expected:
                failures.append({"file": str(fname), "reason": "hash_mismatch"})
        return {"ok": not failures, "failures": failures}


def extract_pack(*, pack_zip: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pack_zip, "r") as zf:
        zf.extractall(dest_dir)
    return dest_dir


def load_suite_from_path(path: Path) -> EvalSuite:
    if path.is_dir():
        return read_suite_dir(path)
    if path.suffix.lower() == ".zip":
        tmp = Path(path.parent) / f".toolkit_eval_unpack_{path.stem}"
        if tmp.exists():
            for p in tmp.rglob("*"):
                if p.is_file():
                    p.unlink()
            for p in sorted([x for x in tmp.rglob("*") if x.is_dir()], reverse=True):
                p.rmdir()
            tmp.rmdir()
        extract_pack(pack_zip=path, dest_dir=tmp)
        return read_suite_dir(tmp)
    raise ValueError(f"unsupported_suite_path:{path}")
