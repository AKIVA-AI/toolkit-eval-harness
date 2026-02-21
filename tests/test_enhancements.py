"""Tests for eval-harness enhancements."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from toolkit_eval_harness.cli import (
    EXIT_CLI_ERROR,
    EXIT_SUCCESS,
    main,
)
from toolkit_eval_harness.io import (
    read_bytes,
    read_json,
    read_jsonl,
    read_text,
    validate_dir_for_read,
    validate_path_for_read,
    validate_path_for_write,
    write_json,
    write_text,
)


# ============================================================================
# Path Validation Tests
# ============================================================================


def test_validate_path_for_read_success(tmp_path: Path) -> None:
    """Test read path validation succeeds with valid file."""
    file_path = tmp_path / "test.json"
    file_path.write_text('{"test": true}', encoding="utf-8")

    result = validate_path_for_read(file_path)
    assert result.is_absolute()
    assert result.is_file()


def test_validate_path_for_read_not_found() -> None:
    """Test read path validation fails with non-existent file."""
    with pytest.raises(FileNotFoundError, match="File not found"):
        validate_path_for_read(Path("/nonexistent/file.json"))


def test_validate_path_for_read_is_directory(tmp_path: Path) -> None:
    """Test read path validation fails when path is directory."""
    with pytest.raises(ValueError, match="not a file"):
        validate_path_for_read(tmp_path)


def test_validate_path_for_write_success(tmp_path: Path) -> None:
    """Test write path validation succeeds."""
    file_path = tmp_path / "output.json"
    result = validate_path_for_write(file_path)
    assert result.is_absolute()


def test_validate_path_for_write_is_directory(tmp_path: Path) -> None:
    """Test write path validation fails when path is directory."""
    with pytest.raises(ValueError, match="is a directory"):
        validate_path_for_write(tmp_path)


def test_validate_dir_for_read_success(tmp_path: Path) -> None:
    """Test directory validation succeeds with valid directory."""
    result = validate_dir_for_read(tmp_path)
    assert result.is_absolute()
    assert result.is_dir()


def test_validate_dir_for_read_not_found() -> None:
    """Test directory validation fails with non-existent directory."""
    with pytest.raises(FileNotFoundError, match="Directory not found"):
        validate_dir_for_read(Path("/nonexistent/dir"))


def test_validate_dir_for_read_is_file(tmp_path: Path) -> None:
    """Test directory validation fails when path is file."""
    file_path = tmp_path / "test.txt"
    file_path.write_text("test", encoding="utf-8")
    
    with pytest.raises(ValueError, match="not a directory"):
        validate_dir_for_read(file_path)


# ============================================================================
# JSON IO Tests
# ============================================================================


def test_read_json_success(tmp_path: Path) -> None:
    """Test reading valid JSON file."""
    file_path = tmp_path / "test.json"
    data = {"key": "value", "number": 42}
    file_path.write_text(json.dumps(data), encoding="utf-8")

    result = read_json(file_path)
    assert result == data


def test_read_json_invalid_json(tmp_path: Path) -> None:
    """Test reading invalid JSON raises ValueError."""
    file_path = tmp_path / "invalid.json"
    file_path.write_text("not valid json", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON"):
        read_json(file_path)


def test_write_json_success(tmp_path: Path) -> None:
    """Test writing JSON file."""
    file_path = tmp_path / "output.json"
    data = {"test": True, "value": 123}

    write_json(file_path, data)

    assert file_path.exists()
    assert json.loads(file_path.read_text()) == data


# ============================================================================
# Text IO Tests
# ============================================================================


def test_read_text_success(tmp_path: Path) -> None:
    """Test reading text file."""
    file_path = tmp_path / "test.txt"
    content = "Hello, World!"
    file_path.write_text(content, encoding="utf-8")

    result = read_text(file_path)
    assert result == content


def test_write_text_success(tmp_path: Path) -> None:
    """Test writing text file."""
    file_path = tmp_path / "output.txt"
    content = "Test content"

    write_text(file_path, content)

    assert file_path.exists()
    assert file_path.read_text() == content


# ============================================================================
# Binary IO Tests
# ============================================================================


def test_read_bytes_success(tmp_path: Path) -> None:
    """Test reading binary file."""
    file_path = tmp_path / "test.bin"
    data = b"\x00\x01\x02\x03"
    file_path.write_bytes(data)

    result = read_bytes(file_path)
    assert result == data


# ============================================================================
# JSONL IO Tests
# ============================================================================


def test_read_jsonl_success(tmp_path: Path) -> None:
    """Test reading JSONL file."""
    file_path = tmp_path / "test.jsonl"
    rows = [{"id": 1}, {"id": 2}, {"id": 3}]
    content = "\n".join(json.dumps(r) for r in rows) + "\n"
    file_path.write_text(content, encoding="utf-8")

    result = list(read_jsonl(file_path))

    assert len(result) == 3
    assert result[0] == {"id": 1}


def test_read_jsonl_skips_empty_lines(tmp_path: Path) -> None:
    """Test JSONL reader skips empty lines."""
    file_path = tmp_path / "test.jsonl"
    content = '{"id": 1}\n\n{"id": 2}\n\n\n{"id": 3}\n'
    file_path.write_text(content, encoding="utf-8")

    result = list(read_jsonl(file_path))

    assert len(result) == 3


def test_read_jsonl_invalid_json(tmp_path: Path) -> None:
    """Test JSONL reader raises on invalid JSON."""
    file_path = tmp_path / "invalid.jsonl"
    content = '{"id": 1}\nnot json\n{"id": 2}\n'
    file_path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON at line 2"):
        list(read_jsonl(file_path))


def test_read_jsonl_non_dict_object(tmp_path: Path) -> None:
    """Test JSONL reader raises on non-dict objects."""
    file_path = tmp_path / "invalid.jsonl"
    content = '{"id": 1}\n["array"]\n{"id": 2}\n'
    file_path.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match="non-dict"):
        list(read_jsonl(file_path))


# ============================================================================
# CLI Tests
# ============================================================================


def test_cli_keygen_creates_files(tmp_path: Path) -> None:
    """Test keygen creates key files."""
    priv_key = tmp_path / "private.pem"
    pub_key = tmp_path / "public.pem"
    
    exit_code = main([
        "keygen",
        "--private-key", str(priv_key),
        "--public-key", str(pub_key),
    ])
    
    assert exit_code == EXIT_SUCCESS
    assert priv_key.exists()
    assert pub_key.exists()


def test_cli_pack_inspect_nonexistent() -> None:
    """Test inspect fails with nonexistent suite."""
    exit_code = main([
        "pack", "inspect",
        "--suite", "/nonexistent",
    ])
    
    assert exit_code == EXIT_CLI_ERROR


def test_cli_pack_verify_nonexistent() -> None:
    """Test verify fails with nonexistent pack."""
    exit_code = main([
        "pack", "verify",
        "--suite", "/nonexistent.zip",
    ])
    
    assert exit_code == EXIT_CLI_ERROR


def test_cli_pack_sign_pack_not_found() -> None:
    """Test sign fails when pack doesn't exist."""
    exit_code = main([
        "pack", "sign",
        "--suite", "/nonexistent.zip",
        "--private-key", "/nonexistent.pem",
    ])
    
    assert exit_code == EXIT_CLI_ERROR


def test_cli_pack_verify_sig_signature_not_found(tmp_path: Path) -> None:
    """Test verify-signature fails when signature doesn't exist."""
    # Create dummy pack (just a file)
    pack = tmp_path / "pack.zip"
    pack.write_bytes(b"dummy")
    
    pub_key = tmp_path / "public.pem"
    pub_key.write_text("dummy", encoding="utf-8")
    
    exit_code = main([
        "pack", "verify-signature",
        "--suite", str(pack),
        "--signature", "/nonexistent.json",
        "--public-key", str(pub_key),
    ])
    
    assert exit_code == EXIT_CLI_ERROR


def test_cli_run_suite_not_found() -> None:
    """Test run fails when suite doesn't exist."""
    exit_code = main([
        "run",
        "--suite", "/nonexistent",
        "--predictions", "/nonexistent.jsonl",
    ])
    
    assert exit_code == EXIT_CLI_ERROR


def test_cli_compare_baseline_not_found(tmp_path: Path) -> None:
    """Test compare fails when baseline doesn't exist."""
    candidate = tmp_path / "candidate.json"
    candidate.write_text('{"suite": {}, "summary": {}, "cases": []}', encoding="utf-8")
    
    exit_code = main([
        "compare",
        "--baseline", "/nonexistent.json",
        "--candidate", str(candidate),
    ])
    
    assert exit_code == EXIT_CLI_ERROR


def test_cli_compare_candidate_not_found(tmp_path: Path) -> None:
    """Test compare fails when candidate doesn't exist."""
    baseline = tmp_path / "baseline.json"
    baseline.write_text('{"suite": {}, "summary": {}, "cases": []}', encoding="utf-8")
    
    exit_code = main([
        "compare",
        "--baseline", str(baseline),
        "--candidate", "/nonexistent.json",
    ])
    
    assert exit_code == EXIT_CLI_ERROR


def test_cli_validate_report_not_found() -> None:
    """Test validate fails when report doesn't exist."""
    exit_code = main([
        "validate-report",
        "--report", "/nonexistent.json",
    ])
    
    assert exit_code == EXIT_CLI_ERROR


def test_cli_validate_report_invalid_json(tmp_path: Path) -> None:
    """Test validate fails with invalid JSON."""
    report = tmp_path / "report.json"
    report.write_text("not valid json", encoding="utf-8")
    
    exit_code = main([
        "validate-report",
        "--report", str(report),
    ])
    
    assert exit_code == EXIT_CLI_ERROR


# ============================================================================
# Edge Case Tests
# ============================================================================


def test_write_json_creates_parent_directory(tmp_path: Path) -> None:
    """Test write creates parent directories."""
    file_path = tmp_path / "subdir" / "nested" / "output.json"
    data = {"nested": True}

    write_json(file_path, data)

    assert file_path.exists()
    assert json.loads(file_path.read_text()) == data


def test_write_text_creates_parent_directory(tmp_path: Path) -> None:
    """Test write creates parent directories."""
    file_path = tmp_path / "subdir" / "output.txt"
    content = "test"

    write_text(file_path, content)

    assert file_path.exists()
    assert file_path.read_text() == content

