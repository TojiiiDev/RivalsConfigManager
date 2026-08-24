"""Tests for app/obj_metadata.py — sidecar logic (no Qt)."""

from __future__ import annotations

from pathlib import Path

from app.models import KIND_FILE, KIND_FOLDER, ConfigItem, Node
from app.obj_metadata import (
    apply_obj_metadata,
    associated_obj,
    delete_metadata,
    is_obj_metadata,
    load_metadata,
    metadata_path_for,
    original_name,
    save_metadata,
    stable_obj_id,
)


def _file_item(tmp_path: Path, name: str = "Rival Skin") -> ConfigItem:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / f"{name}.json"
    path.write_text("{}", encoding="utf-8")
    return ConfigItem(name=name, path=path, kind=KIND_FILE, files=[path], json_files=[path])


def test_metadata_path_file_config(tmp_path: Path) -> None:
    item = _file_item(tmp_path)
    assert metadata_path_for(item) == tmp_path / "Rival Skin.obj.json"


def test_metadata_path_folder_config(tmp_path: Path) -> None:
    folder = tmp_path / "Rival Skin"
    folder.mkdir()
    item = ConfigItem(name="Rival Skin", path=folder, kind=KIND_FOLDER, files=[], json_files=[])
    assert metadata_path_for(item) == folder / "obj.json"


def test_metadata_path_node(tmp_path: Path) -> None:
    node = Node(name="Primary", path=tmp_path / "Primary")
    assert metadata_path_for(node) == tmp_path / "Primary" / "obj.json"


def test_is_obj_metadata() -> None:
    assert is_obj_metadata(Path("Rival Skin.obj.json"))
    assert is_obj_metadata(Path("rival skin.OBJ.JSON"))
    assert is_obj_metadata(Path("obj.json"))
    assert not is_obj_metadata(Path("Rival Skin.json"))
    assert not is_obj_metadata(Path("Rival Skin.obj"))
    assert not is_obj_metadata(Path("config.json"))


def test_save_load_roundtrip(tmp_path: Path, monkeypatch) -> None:
    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))

    item = _file_item(tmp_path / "lib")
    # v2 format: objs list.
    save_metadata(
        item,
        {
            "objs": [
                {
                    "type": "local",
                    "source": "C:/x.obj",
                    "local_path": "obj_cache/abc.obj",
                    "file_name": "x.obj",
                }
            ]
        },
    )
    meta = load_metadata(item)
    assert meta["version"] == 2
    objs = meta["objs"]
    assert len(objs) == 1
    assert objs[0]["type"] == "local"
    assert objs[0]["file_name"] == "x.obj"
    # The real configuration file was not touched.
    assert item.path.read_text(encoding="utf-8") == "{}"


def test_load_missing_and_corrupt(tmp_path: Path) -> None:
    item = _file_item(tmp_path)
    assert load_metadata(item) is None
    (tmp_path / "Rival Skin.obj.json").write_text("{oops", encoding="utf-8")
    assert load_metadata(item) is None


def test_delete_metadata(tmp_path: Path) -> None:
    item = _file_item(tmp_path)
    save_metadata(item, {"objs": [{"type": "local", "source": "x", "local_path": "y", "file_name": "x.obj"}]})
    assert delete_metadata(item)
    assert not (tmp_path / "Rival Skin.obj.json").exists()
    assert not delete_metadata(item)


def test_stable_id_stable_and_distinct(tmp_path: Path) -> None:
    a = _file_item(tmp_path)
    b = _file_item(tmp_path / "other")
    assert stable_obj_id(a) == stable_obj_id(a)
    assert stable_obj_id(a) != stable_obj_id(b)
    assert len(stable_obj_id(a)) == 16


def test_associated_obj_resolution(tmp_path: Path, monkeypatch) -> None:
    import app.config as config_module

    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))

    item = _file_item(tmp_path / "lib")
    cache = config_module.obj_cache_dir()  # already created by obj_cache_dir()
    model = cache / "abc.obj"
    model.write_text("v 0 0 0", encoding="utf-8")

    save_metadata(item, {"objs": [{"type": "local", "source": "x", "local_path": "obj_cache/abc.obj", "file_name": "abc.obj"}]})
    assert associated_obj(item) == model
    assert original_name(item) == "abc.obj"

    model.unlink()
    assert associated_obj(item) is None


def test_apply_obj_metadata_overrides_auto(tmp_path: Path, monkeypatch) -> None:
    import app.config as config_module

    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))

    cache = config_module.obj_cache_dir()  # already created by obj_cache_dir()
    cached = cache / "manual.obj"
    cached.write_text("v 0 0 0", encoding="utf-8")

    node = Node(name="root", path=tmp_path)
    sub = Node(name="sub", path=tmp_path / "sub")
    item = _file_item(tmp_path / "lib")
    node.subdirs.append(sub)
    sub.configs.append(item)

    save_metadata(
        item,
        {"objs": [{"type": "local", "source": "C:/manual.obj", "local_path": "obj_cache/manual.obj", "file_name": "manual.obj"}]},
    )
    apply_obj_metadata(node)
    assert item.obj == cached
    assert item.obj_name == "manual.obj"


# ---------------------------------------------------------------------- #
# v1 -> v2 migration
# ---------------------------------------------------------------------- #
def test_v1_metadata_is_auto_migrated(tmp_path: Path, monkeypatch) -> None:
    """Old v1 single-OBJ sidecar is read as v2 list."""
    import app.config as config_module

    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))

    item = _file_item(tmp_path / "lib")
    cache = config_module.obj_cache_dir()
    model = cache / "old_model.obj"
    model.write_text("v 0 0 0", encoding="utf-8")

    # Write a v1-format sidecar directly.
    import json
    sidecar = tmp_path / "lib" / "Rival Skin.obj.json"
    sidecar.write_text(json.dumps({
        "version": 1,
        "type": "local",
        "source": "C:/original.obj",
        "local_path": "obj_cache/old_model.obj",
        "file_name": "old_model.obj",
    }), encoding="utf-8")

    meta = load_metadata(item)
    assert meta["version"] == 2
    objs = meta["objs"]
    assert len(objs) == 1
    assert objs[0]["file_name"] == "old_model.obj"
    assert objs[0]["type"] == "local"

    # associated_obj still works.
    assert associated_obj(item) == model
    assert original_name(item) == "old_model.obj"


def test_add_multiple_objs_via_metadata(tmp_path: Path, monkeypatch) -> None:
    """Adding OBJs appends — never overwrites."""
    import app.config as config_module
    from app.obj_manager import ObjManager

    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))
    
    cache = config_module.obj_cache_dir()
    manager = ObjManager(cache)
    item = _file_item(tmp_path / "lib")

    src1 = tmp_path / "part1.obj"
    src1.write_text("v 0 0 0", encoding="utf-8")
    src2 = tmp_path / "part2.obj"
    src2.write_text("v 1 0 0", encoding="utf-8")
    src3 = tmp_path / "part3.obj"
    src3.write_text("v 2 0 0", encoding="utf-8")

    manager.import_local(item, src1)
    assert manager.count(item) == 1
    manager.import_local(item, src2)
    assert manager.count(item) == 2
    manager.import_local(item, src3)
    assert manager.count(item) == 3

    from app.obj_metadata import associated_objs, associated_obj_names
    assert len(associated_objs(item)) == 3
    assert [n for n in associated_obj_names(item)] == ["part1.obj", "part2.obj", "part3.obj"]


def test_remove_one_obj_keeps_others(tmp_path: Path, monkeypatch) -> None:
    """Removing one OBJ keeps the others intact."""
    import app.config as config_module
    from app.obj_manager import ObjManager

    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))

    cache = config_module.obj_cache_dir()
    manager = ObjManager(cache)
    item = _file_item(tmp_path / "lib")

    src1 = tmp_path / "part1.obj"
    src1.write_text("v 0 0 0", encoding="utf-8")
    src2 = tmp_path / "part2.obj"
    src2.write_text("v 1 0 0", encoding="utf-8")
    src3 = tmp_path / "part3.obj"
    src3.write_text("v 2 0 0", encoding="utf-8")

    manager.import_local(item, src1)
    manager.import_local(item, src2)
    manager.import_local(item, src3)

    # Remove the middle one (index 1).
    assert manager.count(item) == 3
    assert manager.remove_one(item, 1)
    assert manager.count(item) == 2

    from app.obj_metadata import associated_obj_names
    names = associated_obj_names(item)
    assert "part1.obj" in names
    assert "part3.obj" in names
    assert "part2.obj" not in names


def test_replace_one_obj_keeps_others(tmp_path: Path, monkeypatch) -> None:
    """Replacing one OBJ keeps the others intact."""
    import app.config as config_module
    from app.obj_manager import ObjManager

    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))

    cache = config_module.obj_cache_dir()
    manager = ObjManager(cache)
    item = _file_item(tmp_path / "lib")

    src1 = tmp_path / "part1.obj"
    src1.write_text("v 0 0 0", encoding="utf-8")
    src2 = tmp_path / "part2.obj"
    src2.write_text("v 1 0 0", encoding="utf-8")
    src3 = tmp_path / "part3.obj"
    src3.write_text("v 2 0 0", encoding="utf-8")

    c1 = manager.import_local(item, src1)
    c2 = manager.import_local(item, src2)
    c3 = manager.import_local(item, src3)

    # Replace part2 with new content.
    new_src = tmp_path / "part2_new.obj"
    new_src.write_text("v 9 0 0", encoding="utf-8")
    replaced = manager.replace_one(item, 1, new_src)
    # same index, same cache file path — old content was deleted and rewritten
    assert replaced == c2
    # Re-open: the cache file has been replaced
    assert replaced.read_text(encoding="utf-8") == "v 9 0 0"

    # part1 and part3 unchanged.
    assert c1.read_text(encoding="utf-8") == "v 0 0 0"
    assert c3.read_text(encoding="utf-8") == "v 2 0 0"

    from app.obj_metadata import associated_obj_names
    assert associated_obj_names(item) == ["part1.obj", "part2_new.obj", "part3.obj"]
