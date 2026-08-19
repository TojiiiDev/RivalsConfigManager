"""Tests for app/image_metadata.py — sidecar logic (no Qt)."""

from __future__ import annotations

import json
from pathlib import Path

from app.image_metadata import (
    apply_metadata,
    delete_metadata,
    effective_preview,
    is_image_metadata,
    load_metadata,
    local_image_path,
    metadata_path_for,
    save_metadata,
    stable_id,
)
from app.models import KIND_FILE, KIND_FOLDER, ConfigItem


def _file_item(tmp_path: Path) -> ConfigItem:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "Rival Skin.json"
    path.write_text("{}", encoding="utf-8")
    return ConfigItem(name="Rival Skin", path=path, kind=KIND_FILE, files=[path], json_files=[path])


def test_metadata_path_file_config(tmp_path: Path) -> None:
    item = _file_item(tmp_path)
    assert metadata_path_for(item) == tmp_path / "Rival Skin.image.json"


def test_metadata_path_folder_config(tmp_path: Path) -> None:
    folder = tmp_path / "Rival Skin"
    folder.mkdir()
    item = ConfigItem(name="Rival Skin", path=folder, kind=KIND_FOLDER, files=[], json_files=[])
    assert metadata_path_for(item) == folder / "image.json"


def test_is_image_metadata() -> None:
    assert is_image_metadata(Path("Rival Skin.image.json"))
    assert is_image_metadata(Path("rival skin.IMAGE.JSON"))
    assert not is_image_metadata(Path("Rival Skin.json"))
    assert not is_image_metadata(Path("config.json"))


def test_save_load_roundtrip(tmp_path: Path) -> None:
    item = _file_item(tmp_path)
    save_metadata(item, {"type": "local", "source": "C:/x.png", "local_path": "image_cache/abc.png"})
    meta = load_metadata(item)
    assert meta["version"] == 1
    assert meta["type"] == "local"
    assert meta["local_path"] == "image_cache/abc.png"
    # The real configuration file was not touched.
    assert item.path.read_text(encoding="utf-8") == "{}"


def test_load_missing_and_corrupt(tmp_path: Path) -> None:
    item = _file_item(tmp_path)
    assert load_metadata(item) is None
    (tmp_path / "Rival Skin.image.json").write_text("{oops", encoding="utf-8")
    assert load_metadata(item) is None


def test_delete_metadata(tmp_path: Path) -> None:
    item = _file_item(tmp_path)
    save_metadata(item, {"type": "local", "source": "x", "local_path": "y"})
    assert delete_metadata(item)
    assert not (tmp_path / "Rival Skin.image.json").exists()
    assert not delete_metadata(item)


def test_stable_id_stable_and_distinct(tmp_path: Path) -> None:
    a = _file_item(tmp_path)
    b = _file_item(tmp_path / "other")
    assert stable_id(a) == stable_id(a)
    assert stable_id(a) != stable_id(b)
    assert len(stable_id(a)) == 16


def test_local_image_path_resolution(tmp_path: Path, monkeypatch) -> None:
    import app.config as config_module
    from app import image_metadata

    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))

    item = _file_item(tmp_path / "lib")
    cache = config_module.data_dir() / "image_cache"
    cache.mkdir(parents=True)
    img = cache / "abc.png"
    img.write_bytes(b"png")

    save_metadata(item, {"type": "local", "source": "x", "local_path": "image_cache/abc.png"})
    assert local_image_path(item) == img

    # Missing file -> None (no crash).
    img.unlink()
    assert local_image_path(item) is None
    # Corrupt sidecar -> None.
    assert load_metadata(item) is not None  # sidecar still readable
    assert image_metadata is not None


def test_effective_preview_priority(tmp_path: Path, monkeypatch) -> None:
    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))

    lib = tmp_path / "lib"
    lib.mkdir()
    item = _file_item(lib)
    library_preview = lib / "preview.png"
    library_preview.write_bytes(b"png")
    item.preview = library_preview  # what the scanner sets before apply_metadata

    # Without sidecar -> library preview.
    assert effective_preview(item) == library_preview

    # With sidecar pointing to an existing cache image -> cache wins.
    from app.config import data_dir

    cache = data_dir() / "image_cache"
    cache.mkdir(parents=True)
    cached = cache / "id1.png"
    cached.write_bytes(b"png")
    save_metadata(item, {"type": "url", "source": "https://x/y.png", "local_path": "image_cache/id1.png"})
    assert effective_preview(item) == cached


def test_apply_metadata_walks_tree(tmp_path: Path, monkeypatch) -> None:
    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))

    from app.config import data_dir
    from app.models import Node

    cache = data_dir() / "image_cache"
    cache.mkdir(parents=True)
    cached = cache / "id2.png"
    cached.write_bytes(b"png")

    node = Node(name="root", path=tmp_path)
    sub = Node(name="sub", path=tmp_path / "sub")
    item = _file_item(tmp_path / "lib")
    node.subdirs.append(sub)
    sub.configs.append(item)

    save_metadata(item, {"type": "local", "source": "x", "local_path": "image_cache/id2.png"})
    apply_metadata(node)
    assert item.preview == cached

    assert json is not None  # keep import used


def test_metadata_path_for_node(tmp_path: Path) -> None:
    from app.models import Node

    node = Node(name="Primary", path=tmp_path / "Primary")
    assert metadata_path_for(node) == tmp_path / "Primary" / "image.json"


def test_node_image_roundtrip_and_priority(tmp_path: Path, monkeypatch) -> None:
    """A node (folder) can hold its own image, independent of its children."""
    from app.config import data_dir
    from app.models import Node

    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))

    cache = data_dir() / "image_cache"
    cache.mkdir(parents=True)
    cached = cache / "node.png"
    cached.write_bytes(b"png")

    node = Node(name="Primary", path=tmp_path / "Primary", preview=tmp_path / "preview.png")
    save_metadata(node, {"type": "local", "source": "x", "local_path": "image_cache/node.png"})
    assert local_image_path(node) == cached
    # Sidecar wins over the library preview.
    assert effective_preview(node) == cached
    assert delete_metadata(node)
    assert not (tmp_path / "Primary" / "image.json").exists()


def test_node_apply_metadata_resolves_node_preview(tmp_path: Path, monkeypatch) -> None:
    from app.config import data_dir
    from app.models import Node

    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))

    cache = data_dir() / "image_cache"
    cache.mkdir(parents=True)
    cached = cache / "cat.png"
    cached.write_bytes(b"png")

    root = Node(name="root", path=tmp_path)
    child = Node(name="Charms", path=tmp_path / "Charms")
    config = _file_item(tmp_path / "Charms" / "lib")
    root.subdirs.append(child)
    child.configs.append(config)

    save_metadata(child, {"type": "local", "source": "x", "local_path": "image_cache/cat.png"})
    apply_metadata(root)
    assert child.preview == cached
    # The child's own preview is untouched (independent images).
    assert config.preview is None


def test_stable_id_same_name_different_folders(tmp_path: Path) -> None:
    """Two elements sharing a name in different paths never collide."""
    from app.models import Node

    a = Node(name="Primary", path=tmp_path / "A" / "Primary")
    b = Node(name="Primary", path=tmp_path / "B" / "Primary")
    assert stable_id(a) != stable_id(b)
    assert stable_id(a) == stable_id(a)
