"""Suite packs: a zip holding ``suite.json`` and ``cases.jsonl`` plus a SHA-256 manifest.

Integrity model:

- ``verify_pack`` checks every member against ``manifest.json`` and rejects members the
  manifest does not list. The manifest lives inside the same zip, so this detects
  accidental corruption and partial edits, **not** deliberate tampering: anyone who can
  rewrite a file can also rewrite its hash.
- Tamper evidence comes from a detached Ed25519 signature over the whole pack
  (``toolkit-eval pack sign``), which ``toolkit-eval run`` checks when one is supplied.
- Loading a pack reads it into memory once and verifies it; nothing is extracted to disk.
"""

from __future__ import annotations

import hashlib
import io
import json
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .hashing import sha256_file
from .suite import EvalSuite, parse_suite, read_suite_dir

SUITE_FILES = ("suite.json", "cases.jsonl")
# Members that are allowed in a pack without a manifest entry.
_UNHASHED_MEMBERS = frozenset({"manifest.json", "pack.json"})


class PackVerificationError(ValueError):
    """Raised when a suite pack fails its manifest check."""

    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        detail = result.get("reason") or ", ".join(
            f"{f.get('file')}:{f.get('reason')}" for f in result.get("failures", [])
        )
        super().__init__(f"pack_verification_failed:{detail}")


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


def _verify_zip(zf: zipfile.ZipFile) -> dict[str, Any]:
    all_names = zf.namelist()
    names = set(all_names)
    if "manifest.json" not in names:
        return {"ok": False, "reason": "missing_manifest", "failures": []}
    try:
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"ok": False, "reason": "invalid_manifest", "failures": []}
    files = manifest.get("files") if isinstance(manifest, dict) else None
    if not isinstance(files, dict):
        return {"ok": False, "reason": "invalid_manifest", "failures": []}

    failures: list[dict[str, str]] = []
    for dup in sorted({n for n in all_names if all_names.count(n) > 1}):
        failures.append({"file": dup, "reason": "duplicate_member"})
    for required in SUITE_FILES:
        if required not in files:
            failures.append({"file": required, "reason": "missing_from_manifest"})
    for fname, meta in files.items():
        if fname not in names:
            failures.append({"file": str(fname), "reason": "missing"})
            continue
        expected = str(meta.get("sha256") or "") if isinstance(meta, dict) else ""
        if hashlib.sha256(zf.read(fname)).hexdigest() != expected:
            failures.append({"file": str(fname), "reason": "hash_mismatch"})
    for name in sorted(names - set(files) - _UNHASHED_MEMBERS):
        failures.append({"file": name, "reason": "not_in_manifest"})
    return {"ok": not failures, "failures": failures}


def verify_pack_bytes(data: bytes) -> dict[str, Any]:
    """Verify an in-memory pack against its manifest. See the module docstring for limits."""
    try:
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            return _verify_zip(zf)
    except zipfile.BadZipFile:
        return {"ok": False, "reason": "invalid_zip", "failures": []}


def verify_pack(*, pack_zip: Path) -> dict[str, Any]:
    """Verify a pack file's members against its ``manifest.json``.

    Returns ``{"ok": bool, "failures": [...]}`` (plus ``reason`` for structural errors).
    """
    return verify_pack_bytes(pack_zip.read_bytes())


def load_suite_from_zip_bytes(data: bytes) -> EvalSuite:
    """Verify an in-memory pack and parse its suite without writing anything to disk.

    Raises :class:`PackVerificationError` if the manifest check fails.
    """
    result = verify_pack_bytes(data)
    if not result.get("ok"):
        raise PackVerificationError(result)
    with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
        return parse_suite(
            suite_json=zf.read("suite.json").decode("utf-8"),
            cases_jsonl=zf.read("cases.jsonl").decode("utf-8"),
        )


def extract_pack(*, pack_zip: Path, dest_dir: Path) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    resolved_dest = dest_dir.resolve()
    with zipfile.ZipFile(pack_zip, "r") as zf:
        for member in zf.infolist():
            member_path = (resolved_dest / member.filename).resolve()
            try:
                member_path.relative_to(resolved_dest)
            except ValueError:
                raise ValueError(
                    f"zip_path_traversal_blocked:{member.filename} "
                    f"resolves outside destination directory"
                ) from None
        zf.extractall(dest_dir)
    return dest_dir


def load_suite_from_path(path: Path) -> EvalSuite:
    """Load a suite from a directory or a ``.zip`` pack.

    A pack is verified against its manifest first (:class:`PackVerificationError` on
    failure). Signature checks are separate; see ``toolkit-eval run --signature``.
    """
    if path.is_dir():
        return read_suite_dir(path)
    if path.suffix.lower() == ".zip":
        return load_suite_from_zip_bytes(path.read_bytes())
    raise ValueError(f"unsupported_suite_path:{path}")
