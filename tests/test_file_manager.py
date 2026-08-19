"""Tests for app/file_manager.py — activation copies."""

from __future__ import annotations

import json
from pathlib import Path

from app.backup_manager import BackupManager
from app.file_manager import FileManager
from app.models import KIND_FILE, KIND_FOLDER, ConfigItem
from app.scanner import scan_library


def _manager(tmp_path: Path) -> FileManager:
    return FileManager(BackupManager(tmp_path / "backups"))


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_activate_single_file(library: Path, fleasion_dir: Path, tmp_path: Path) -> None:
    node = scan_library(library).node
    charms = next(s for s in node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")

    result = _manager(tmp_path).activate(item, fleasion_dir)
    assert result.ok
    assert (fleasion_dir / "nemesis charm.json").exists()
    assert "nemesis charm.json" in result.copied


def test_activate_copies_dependencies(library: Path, fleasion_dir: Path, tmp_path: Path) -> None:
    node = scan_library(library).node
    skins = next(s for s in node.subdirs if s.name == "rivals skins")
    secondary = next(s for s in skins.subdirs if s.name == "Secondary")
    gun = next(s for s in secondary.subdirs if s.name == "Hand gun")
    item = next(c for c in gun.configs if c.name == "Pixelhandgun")

    result = _manager(tmp_path).activate(item, fleasion_dir)
    assert result.ok
    assert (fleasion_dir / "Pixelhandgun.json").exists()
    assert (fleasion_dir / "Pixelboddy.obj").exists()
    assert not (fleasion_dir / "pxl mag.obj").exists()


def test_activate_folder_config(library: Path, fleasion_dir: Path, tmp_path: Path) -> None:
    node = scan_library(library).node
    textures = next(s for s in node.subdirs if s.name == "Texture and skyboxes")
    item = next(c for c in textures.configs if c.name == "Texture packs")
    assert item.kind == KIND_FOLDER

    result = _manager(tmp_path).activate(item, fleasion_dir)
    assert result.ok
    assert (fleasion_dir / "Minecraft_Classic.json").exists()
    assert (fleasion_dir / "preview.png").exists()


def test_activate_backs_up_existing(library: Path, fleasion_dir: Path, tmp_path: Path) -> None:
    # Pre-existing file with the same name, different content.
    (fleasion_dir / "nemesis charm.json").write_text('{"old": true}', encoding="utf-8")

    node = scan_library(library).node
    charms = next(s for s in node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")

    manager = _manager(tmp_path)
    result = manager.activate(item, fleasion_dir)
    assert result.ok
    assert "nemesis charm.json" in result.backed_up

    backups = manager.backup_manager.list_backups()
    assert len(backups) == 1
    backed = backups[0].folder / "nemesis charm.json"
    assert backed.exists()
    assert backed.read_text(encoding="utf-8") == '{"old": true}'


def test_activate_invalid_json_aborts(library: Path, fleasion_dir: Path, tmp_path: Path) -> None:
    node = scan_library(library).node
    charms = next(s for s in node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")
    item.json_files[0].write_text("{not valid", encoding="utf-8")

    result = _manager(tmp_path).activate(item, fleasion_dir)
    assert not result.ok
    assert result.errors
    assert any("JSON invalide" in e for e in result.errors)
    assert not (fleasion_dir / "nemesis charm.json").exists()


def test_activate_missing_file_reports_error(fleasion_dir: Path, tmp_path: Path) -> None:
    item = ConfigItem(
        name="ghost",
        path=tmp_path / "ghost.json",
        kind=KIND_FILE,
        files=[tmp_path / "ghost.json"],
        json_files=[tmp_path / "ghost.json"],
    )
    result = _manager(tmp_path).activate(item, fleasion_dir)
    assert not result.ok
    assert any("manquant" in e for e in result.errors)


def test_activate_creates_dest_folder(library: Path, tmp_path: Path) -> None:
    dest = tmp_path / "does" / "not" / "exist"
    node = scan_library(library).node
    charms = next(s for s in node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")
    result = _manager(tmp_path).activate(item, dest)
    assert result.ok
    assert (dest / "nemesis charm.json").exists()


def test_activate_dest_is_file_reports_error(library: Path, tmp_path: Path) -> None:
    dest_file = tmp_path / "blocked"
    dest_file.write_text("x", encoding="utf-8")
    node = scan_library(library).node
    charms = next(s for s in node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")
    result = _manager(tmp_path).activate(item, dest_file)
    assert not result.ok
    assert result.errors


def test_activate_paths_with_spaces(library: Path, fleasion_dir: Path, tmp_path: Path) -> None:
    assert " " in str(library)  # fixture guarantees spaces
    node = scan_library(library).node
    charms = next(s for s in node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")
    result = _manager(tmp_path).activate(item, fleasion_dir)
    assert result.ok


def test_activate_without_backup_overwrites(library: Path, fleasion_dir: Path, tmp_path: Path) -> None:
    (fleasion_dir / "nemesis charm.json").write_text('{"old": true}', encoding="utf-8")
    node = scan_library(library).node
    charms = next(s for s in node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")

    manager = _manager(tmp_path)
    result = manager.activate(item, fleasion_dir, backup_before_overwrite=False)
    assert result.ok
    assert result.backed_up == []
    assert manager.backup_manager.list_backups() == []


def test_activate_copies_stem_matched_obj(tmp_path: Path, fleasion_dir: Path) -> None:
    """Skin.json + Skin.obj: activation copies the model next to the JSON."""
    folder = tmp_path / "lib" / "rivals skins" / "Primary" / "Assault Rifle"
    folder.mkdir(parents=True)
    _write_json(folder / "Rival Skin.json", {"replacement_rules": []})
    _write_json(folder / "Other.json", {"replacement_rules": []})
    (folder / "Rival Skin.obj").write_text("v 0 0 0", encoding="utf-8")

    node = scan_library(tmp_path / "lib").node
    skins = next(s for s in node.subdirs if s.name == "rivals skins")
    primary = next(s for s in skins.subdirs if s.name == "Primary")
    rifle = next(s for s in primary.subdirs if s.name == "Assault Rifle")
    item = next(c for c in rifle.configs if c.name == "Rival Skin")
    assert item.obj is not None

    result = _manager(tmp_path).activate(item, fleasion_dir)
    assert result.ok
    assert (fleasion_dir / "Rival Skin.json").exists()
    assert (fleasion_dir / "Rival Skin.obj").exists()
    assert "Rival Skin.obj" in result.copied


def test_activate_copies_manually_associated_obj(tmp_path: Path, fleasion_dir: Path) -> None:
    """A manually imported obj (app cache) is copied under its original name."""
    folder = tmp_path / "lib" / "Charms"
    folder.mkdir(parents=True)
    _write_json(folder / "Rival Skin.json", {"replacement_rules": []})

    item = ConfigItem(
        name="Rival Skin",
        path=folder / "Rival Skin.json",
        kind=KIND_FILE,
        files=[folder / "Rival Skin.json"],
        json_files=[folder / "Rival Skin.json"],
    )
    # Simulate a manual import: cache copy + sidecar metadata.
    from app.obj_metadata import save_metadata as save_obj_metadata
    from app.obj_manager import ObjManager

    cache = tmp_path / "obj_cache"
    cached = ObjManager(cache).cache_file_for(item)
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_text("v 0 0 0", encoding="utf-8")
    save_obj_metadata(
        item,
        {
            "type": "local",
            "source": "C:/original.obj",
            "local_path": str(cached),
            "file_name": "original.obj",
        },
    )

    from app.obj_metadata import apply_obj_metadata
    from app.models import Node

    node = Node(name="root", path=tmp_path / "lib")
    node.configs.append(item)
    apply_obj_metadata(node)
    assert item.obj == cached
    assert item.obj_name == "original.obj"

    result = _manager(tmp_path).activate(item, fleasion_dir)
    assert result.ok
    assert (fleasion_dir / "Rival Skin.json").exists()
    assert (fleasion_dir / "original.obj").exists()
    assert "original.obj" in result.copied
    # The real files were never touched.
    assert cached.read_text(encoding="utf-8") == "v 0 0 0"


def test_activate_missing_associated_obj_reports_error(tmp_path: Path, fleasion_dir: Path) -> None:
    folder = tmp_path / "lib" / "Charms"
    folder.mkdir(parents=True)
    _write_json(folder / "Rival Skin.json", {"replacement_rules": []})
    item = ConfigItem(
        name="Rival Skin",
        path=folder / "Rival Skin.json",
        kind=KIND_FILE,
        files=[folder / "Rival Skin.json"],
        json_files=[folder / "Rival Skin.json"],
        obj=tmp_path / "ghost.obj",
        obj_name="ghost.obj",
    )
    result = _manager(tmp_path).activate(item, fleasion_dir)
    assert not result.ok
    assert any("manquant" in e for e in result.errors)


# ---------------------------------------------------------------------- #
# remove_copies
# ---------------------------------------------------------------------- #

def test_remove_copies_removes_only_expected(library: Path, fleasion_dir: Path, tmp_path: Path) -> None:
    """Only the item's own files are removed; the rest stays untouched."""
    node = scan_library(library).node
    charms = next(s for s in node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")

    manager = _manager(tmp_path)
    manager.activate(item, fleasion_dir)
    # A file that does not belong to this item.
    (fleasion_dir / "other.json").write_text("{}", encoding="utf-8")

    result = manager.remove_copies(item, fleasion_dir)
    assert result.errors == []
    assert result.removed == ["nemesis charm.json"]
    assert not (fleasion_dir / "nemesis charm.json").exists()
    assert (fleasion_dir / "other.json").exists()
    # The library original is intact.
    assert (library / "Charms" / "nemesis charm.json").exists()


def test_remove_copies_removes_obj_too(library: Path, fleasion_dir: Path, tmp_path: Path) -> None:
    node = scan_library(library).node
    charms = next(s for s in node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")
    item.obj = tmp_path / "lib" / "model.obj"
    item.obj_name = "model.obj"

    (fleasion_dir / "nemesis charm.json").write_text("{}", encoding="utf-8")
    (fleasion_dir / "model.obj").write_text("v 0 0 0", encoding="utf-8")

    result = _manager(tmp_path).remove_copies(item, fleasion_dir)
    assert result.errors == []
    assert set(result.removed) == {"nemesis charm.json", "model.obj"}


def test_remove_copies_nothing_when_absent(library: Path, fleasion_dir: Path, tmp_path: Path) -> None:
    node = scan_library(library).node
    charms = next(s for s in node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")

    result = _manager(tmp_path).remove_copies(item, fleasion_dir)
    assert result.removed == []
    assert result.errors == []


def test_remove_copies_backs_up_before_removal(library: Path, fleasion_dir: Path, tmp_path: Path) -> None:
    """Removed files are first copied into a backup (safety net)."""
    node = scan_library(library).node
    charms = next(s for s in node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")

    (fleasion_dir / "nemesis charm.json").write_text('{"active": true}', encoding="utf-8")
    manager = _manager(tmp_path)

    result = manager.remove_copies(item, fleasion_dir)
    assert result.removed == ["nemesis charm.json"]
    backups = manager.backup_manager.list_backups()
    assert len(backups) == 1
    backed = backups[0].folder / "nemesis charm.json"
    assert backed.exists()
    assert backed.read_text(encoding="utf-8") == '{"active": true}'


def test_remove_copies_without_backup_overwrites_setting(library: Path, fleasion_dir: Path, tmp_path: Path) -> None:
    node = scan_library(library).node
    charms = next(s for s in node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")
    (fleasion_dir / "nemesis charm.json").write_text("{}", encoding="utf-8")

    manager = _manager(tmp_path)
    result = manager.remove_copies(item, fleasion_dir, backup_before_overwrite=False)
    assert result.removed == ["nemesis charm.json"]
    assert manager.backup_manager.list_backups() == []
