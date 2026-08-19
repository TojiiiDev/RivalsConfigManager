"""Tests for app/obj_manager.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.models import KIND_FILE, ConfigItem
from app.obj_manager import ObjError, ObjManager
from app.obj_metadata import associated_obj, load_metadata


def _item(tmp_path: Path, name: str = "Rival Skin") -> ConfigItem:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"{name}.json"
    path.write_text("{}", encoding="utf-8")
    (tmp_path / f"{name}.obj").write_text("v 0 0 0", encoding="utf-8")
    return ConfigItem(name=name, path=path, kind=KIND_FILE, files=[path], json_files=[path])


def _write_obj(path: Path, body: str = "v 0 0 0\nv 1 0 0\nf 1 2") -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_import_local_copies_and_writes_metadata(tmp_path: Path, monkeypatch) -> None:
    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))
    manager = ObjManager()
    item = _item(tmp_path / "lib")
    source = _write_obj(tmp_path / "model.obj")

    dest = manager.import_local(item, source)

    assert dest.is_file()
    assert dest.read_text(encoding="utf-8") == "v 0 0 0\nv 1 0 0\nf 1 2"
    meta = load_metadata(item)
    assert meta["type"] == "local"
    assert meta["source"] == str(source)
    assert meta["file_name"] == "model.obj"
    assert meta["local_path"] == f"obj_cache/{dest.name}"
    # The real configuration files were not touched.
    assert (tmp_path / "lib" / "Rival Skin.json").read_text(encoding="utf-8") == "{}"
    assert (tmp_path / "lib" / "Rival Skin.obj").read_text(encoding="utf-8") == "v 0 0 0"


def test_import_local_missing_file(tmp_path: Path) -> None:
    manager = ObjManager(tmp_path / "cache")
    item = _item(tmp_path / "lib")
    with pytest.raises(ObjError, match="introuvable"):
        manager.import_local(item, tmp_path / "ghost.obj")


def test_import_local_wrong_format(tmp_path: Path) -> None:
    manager = ObjManager(tmp_path / "cache")
    item = _item(tmp_path / "lib")
    source = tmp_path / "notes.txt"
    source.write_text("hello", encoding="utf-8")
    with pytest.raises(ObjError, match="Format non supporté"):
        manager.import_local(item, source)


def test_import_local_empty_file(tmp_path: Path) -> None:
    manager = ObjManager(tmp_path / "cache")
    item = _item(tmp_path / "lib")
    source = tmp_path / "empty.obj"
    source.write_text("   \n  ", encoding="utf-8")
    with pytest.raises(ObjError, match="vide|illisible"):
        manager.import_local(item, source)


def test_import_local_paths_with_spaces(tmp_path: Path) -> None:
    manager = ObjManager(tmp_path / "cache dir")
    item = _item(tmp_path / "my library")
    source = _write_obj(tmp_path / "my model.obj")
    dest = manager.import_local(item, source)
    assert dest.is_file()


def test_import_local_replaces_previous(tmp_path: Path) -> None:
    manager = ObjManager(tmp_path / "cache")
    item = _item(tmp_path / "lib")
    first = manager.import_local(item, _write_obj(tmp_path / "a.obj"))
    second = manager.import_local(item, _write_obj(tmp_path / "b.obj", "v 5 5 5"))
    assert first == second  # same stable id -> same cache file
    assert second.read_text(encoding="utf-8") == "v 5 5 5"


def test_remove_deletes_metadata_and_cache(tmp_path: Path) -> None:
    manager = ObjManager(tmp_path / "cache")
    item = _item(tmp_path / "lib")
    dest = manager.import_local(item, _write_obj(tmp_path / "source.obj"))
    assert dest.is_file()

    manager.remove(item)
    assert not dest.exists()
    assert load_metadata(item) is None
    # Real configuration files still there.
    assert (tmp_path / "lib" / "Rival Skin.json").exists()
    assert (tmp_path / "lib" / "Rival Skin.obj").exists()


def test_remove_without_obj_is_noop(tmp_path: Path) -> None:
    manager = ObjManager(tmp_path / "cache")
    item = _item(tmp_path / "lib")
    manager.remove(item)  # must not raise
    assert (tmp_path / "lib" / "Rival Skin.json").exists()


def test_validate_obj_file_rejects_unreadable(tmp_path: Path, monkeypatch) -> None:
    from app.obj_manager import validate_obj_file

    path = tmp_path / "locked.obj"
    path.write_text("v 0 0 0", encoding="utf-8")

    def _deny(*args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_bytes", _deny)
    with pytest.raises(ObjError, match="Permission"):
        validate_obj_file(path)
