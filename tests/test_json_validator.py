"""Tests for app/json_validator.py."""

from __future__ import annotations

import json
from pathlib import Path

from app.json_validator import dependency_files, validate_file, validate_files


def test_valid_json(tmp_path: Path) -> None:
    f = tmp_path / "ok.json"
    f.write_text('{"a": 1}', encoding="utf-8")
    ok, err = validate_file(f)
    assert ok
    assert err == ""


def test_invalid_json(tmp_path: Path) -> None:
    f = tmp_path / "broken.json"
    f.write_text('{"a": 1,}', encoding="utf-8")
    ok, err = validate_file(f)
    assert not ok
    assert "broken.json" in err
    assert "ligne" in err


def test_empty_file_is_invalid(tmp_path: Path) -> None:
    f = tmp_path / "empty.json"
    f.write_text("", encoding="utf-8")
    ok, _ = validate_file(f)
    assert not ok


def test_missing_file(tmp_path: Path) -> None:
    ok, err = validate_file(tmp_path / "absent.json")
    assert not ok
    assert "introuvable" in err


def test_bom_utf8_accepted(tmp_path: Path) -> None:
    f = tmp_path / "bom.json"
    f.write_bytes(b"\xef\xbb\xbf{\"a\": 1}")
    ok, _ = validate_file(f)
    assert ok


def test_validate_files_collects_errors(tmp_path: Path) -> None:
    good = tmp_path / "good.json"
    good.write_text("{}", encoding="utf-8")
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    ok, errors = validate_files([good, bad])
    assert not ok
    assert len(errors) == 1
    assert "bad.json" in errors[0]


def test_dependency_files_finds_local_references(tmp_path: Path) -> None:
    folder = tmp_path / "weapon"
    folder.mkdir()
    config = folder / "skin.json"
    config.write_text(
        json.dumps(
            {
                "replacement_rules": [
                    {"cdn_url": "Pixelboddy.obj"},
                    {"cdn_url": "https://example.com/remote.obj"},
                ]
            }
        ),
        encoding="utf-8",
    )
    (folder / "Pixelboddy.obj").write_text("x", encoding="utf-8")
    deps = dependency_files(config, folder)
    assert [d.name for d in deps] == ["Pixelboddy.obj"]


def test_dependency_files_windows_path(tmp_path: Path) -> None:
    folder = tmp_path / "weapon"
    folder.mkdir()
    config = folder / "skin.json"
    config.write_text(
        json.dumps({"mesh": "C:\\\\Users\\\\test\\\\My Skin\\\\blade.obj"}),
        encoding="utf-8",
    )
    (folder / "blade.obj").write_text("x", encoding="utf-8")
    deps = dependency_files(config, folder)
    assert [d.name for d in deps] == ["blade.obj"]


def test_dependency_files_invalid_json_safe(tmp_path: Path) -> None:
    folder = tmp_path / "weapon"
    folder.mkdir()
    config = folder / "broken.json"
    config.write_text("{oops", encoding="utf-8")
    assert dependency_files(config, folder) == []
