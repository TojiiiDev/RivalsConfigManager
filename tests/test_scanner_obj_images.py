"""Scanner tests: hierarchical images (nodes) and deterministic OBJ detection."""

from __future__ import annotations

from pathlib import Path

from app.models import KIND_FILE, KIND_FOLDER
from app.scanner import scan_library


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"replacement_rules": []}', encoding="utf-8")


# ---------------------------------------------------------------------- #
# Hierarchical images (nodes)
# ---------------------------------------------------------------------- #
def test_node_image_from_sidecar(tmp_path: Path, monkeypatch) -> None:
    from app.config import data_dir
    from app.image_manager import ImageManager
    from app.models import Node

    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))

    root = tmp_path / "lib"
    write_json(root / "rivals skins" / "Primary" / "Assault Rifle" / "ak-47.json", {})

    # Put a cached image + sidecar on the *Primary* node.
    cache = data_dir() / "image_cache"
    cache.mkdir(parents=True)
    img = cache / "nodeimg.png"
    img.write_bytes(b"png")
    primary = Node(name="Primary", path=root / "rivals skins" / "Primary")
    ImageManager(cache).save_downloaded(primary, "https://x/y.png", img)

    node = scan_library(root).node
    skins = next(s for s in node.subdirs if s.name == "rivals skins")
    primary_node = next(s for s in skins.subdirs if s.name == "Primary")
    assert primary_node.preview == img
    # Children keep their own (absent) image: the category image does NOT
    # leak into the children.
    rifle = next(s for s in primary_node.subdirs if s.name == "Assault Rifle")
    assert all(c.preview is None for c in rifle.configs)


def test_node_image_distinct_from_other_node_same_name(tmp_path: Path, monkeypatch) -> None:
    """Two nodes sharing a name in different folders get different images."""
    from app.config import data_dir
    from app.image_manager import ImageManager
    from app.models import Node

    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))

    root = tmp_path / "lib"
    write_json(root / "A" / "Primary" / "x.json", {})
    write_json(root / "B" / "Primary" / "y.json", {})

    cache = data_dir() / "image_cache"
    cache.mkdir(parents=True)
    img_a = cache / "a.png"
    img_b = cache / "b.png"
    img_a.write_bytes(b"png")
    img_b.write_bytes(b"png")
    manager = ImageManager(cache)

    node_a = Node(name="Primary", path=root / "A" / "Primary")
    node_b = Node(name="Primary", path=root / "B" / "Primary")
    manager.save_downloaded(node_a, "https://x/a.png", img_a)
    manager.save_downloaded(node_b, "https://x/b.png", img_b)

    node = scan_library(root).node
    a_primary = next(s for s in node.subdirs if s.name == "A").subdirs[0]
    b_primary = next(s for s in node.subdirs if s.name == "B").subdirs[0]
    assert a_primary.preview == img_a
    assert b_primary.preview == img_b


def test_node_image_deleted_returns_to_placeholder(tmp_path: Path, monkeypatch) -> None:
    from app.config import data_dir
    from app.image_manager import ImageManager
    from app.models import Node

    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))

    root = tmp_path / "lib"
    write_json(root / "Charms" / "c.json", {})
    cache = data_dir() / "image_cache"
    cache.mkdir(parents=True)
    img = cache / "c.png"
    img.write_bytes(b"png")
    manager = ImageManager(cache)
    charms = Node(name="Charms", path=root / "Charms")
    manager.save_downloaded(charms, "https://x/c.png", img)

    node = scan_library(root).node
    charms_node = next(s for s in node.subdirs if s.name == "Charms")
    assert charms_node.preview == img

    manager.remove(charms)
    node = scan_library(root).node
    charms_node = next(s for s in node.subdirs if s.name == "Charms")
    assert charms_node.preview is None


# ---------------------------------------------------------------------- #
# OBJ auto-detection (deterministic)
# ---------------------------------------------------------------------- #
def test_obj_stem_match(tmp_path: Path) -> None:
    """Skin.json + Skin.obj -> the model belongs to the config."""
    root = tmp_path / "lib"
    folder = root / "rivals skins" / "Primary" / "Assault Rifle"
    # Two JSONs so the folder is a container (single JSON + obj would make
    # the whole folder one configuration).
    write_json(folder / "Rival Skin.json", {})
    write_json(folder / "Other.json", {})
    (folder / "Rival Skin.obj").write_text("v 0 0 0", encoding="utf-8")

    node = scan_library(root).node
    skins = next(s for s in node.subdirs if s.name == "rivals skins")
    primary = next(s for s in skins.subdirs if s.name == "Primary")
    rifle = next(s for s in primary.subdirs if s.name == "Assault Rifle")
    config = next(c for c in rifle.configs if c.name == "Rival Skin")
    assert config.obj == folder / "Rival Skin.obj"
    assert config.obj_name == "Rival Skin.obj"
    assert "Rival Skin.obj" in {f.name for f in config.files}
    # The other config has no model.
    other = next(c for c in rifle.configs if c.name == "Other")
    assert other.obj is None


def test_obj_stem_match_ambiguous_name_not_guessed(tmp_path: Path) -> None:
    """A model whose name matches no JSON exactly is NOT attached by guess."""
    root = tmp_path / "lib"
    folder = root / "rivals skins" / "Secondary" / "Hand gun"
    write_json(folder / "Pixelhandgun (1).json", {})
    write_json(folder / "other.json", {})
    (folder / "Pixelboddy.obj").write_text("v 0 0 0", encoding="utf-8")

    node = scan_library(root).node
    skins = next(s for s in node.subdirs if s.name == "rivals skins")
    secondary = next(s for s in skins.subdirs if s.name == "Secondary")
    gun = next(s for s in secondary.subdirs if s.name == "Hand gun")
    config = next(c for c in gun.configs if c.name == "Pixelhandgun (1)")
    # No exact stem match, JSON content does not reference it -> no guess.
    assert config.obj is None
    assert "Pixelboddy.obj" not in {f.name for f in config.files}


def test_obj_folder_config_single_model(tmp_path: Path) -> None:
    """A folder config with exactly one model -> unambiguous association."""
    root = tmp_path / "lib"
    pack = root / "Texture packs"
    write_json(pack / "config.json", {})
    (pack / "model.obj").write_text("v 0 0 0", encoding="utf-8")

    node = scan_library(root).node
    config = next(c for c in node.configs if c.name == "Texture packs")
    assert config.kind == KIND_FOLDER
    assert config.obj == pack / "model.obj"
    assert "model.obj" in {f.name for f in config.files}


def test_obj_folder_config_multiple_models_no_single_association(tmp_path: Path) -> None:
    """Several models in a folder config: all copied, first is primary."""
    root = tmp_path / "lib"
    pack = root / "pack"
    write_json(pack / "config.json", {})
    (pack / "body.obj").write_text("v 0 0 0", encoding="utf-8")
    (pack / "mag.obj").write_text("v 0 0 0", encoding="utf-8")

    node = scan_library(root).node
    config = next(c for c in node.configs if c.name == "pack")
    # v2: multi-OBJ — the first is the primary association
    assert config.obj is not None
    assert len(config.objs) == 2
    names = {f.name for f in config.files}
    assert "body.obj" in names and "mag.obj" in names


def test_obj_sidecar_is_not_a_config(tmp_path: Path) -> None:
    """A ``.obj.json`` sidecar must never become a configuration."""
    root = tmp_path / "lib"
    folder = root / "rivals skins"
    write_json(folder / "Rival Skin.json", {})
    (folder / "Rival Skin.obj.json").write_text('{"version": 1, "type": "local"}', encoding="utf-8")

    node = scan_library(root).node
    skins = next(s for s in node.subdirs if s.name == "rivals skins")
    assert [c.name for c in skins.configs] == ["Rival Skin"]


def test_obj_sidecar_excluded_from_folder_config(tmp_path: Path) -> None:
    """A folder config's obj.json is not copied with the configuration."""
    root = tmp_path / "lib"
    pack = root / "pack"
    write_json(pack / "config.json", {})
    (pack / "model.obj").write_text("v 0 0 0", encoding="utf-8")
    (pack / "obj.json").write_text('{"version": 1, "type": "local"}', encoding="utf-8")

    node = scan_library(root).node
    config = next(c for c in node.configs if c.name == "pack")
    names = {f.name for f in config.files}
    assert names == {"config.json", "model.obj"}
    assert "obj.json" not in names


def test_manual_obj_association_survives_scan(tmp_path: Path, monkeypatch) -> None:
    """A manually imported obj (cache + sidecar) is resolved after a scan."""
    from app.config import data_dir
    from app.obj_manager import ObjManager

    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))

    root = tmp_path / "lib"
    folder = root / "Charms"
    write_json(folder / "Rival Skin.json", {})

    result = scan_library(root)
    charms = next(s for s in result.node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "Rival Skin")
    assert item.obj is None

    source = tmp_path / "model.obj"
    source.write_text("v 0 0 0", encoding="utf-8")
    ObjManager().import_local(item, source)

    result = scan_library(root)
    charms = next(s for s in result.node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "Rival Skin")
    assert item.obj is not None
    assert item.obj.is_relative_to(data_dir() / "obj_cache")
    assert item.obj_name == "model.obj"
    # The real files were never modified.
    assert (folder / "Rival Skin.json").exists()
