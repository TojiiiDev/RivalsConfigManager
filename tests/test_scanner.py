"""Tests for app/scanner.py."""

from __future__ import annotations

from pathlib import Path

from app.models import KIND_FILE, KIND_FOLDER
from app.scanner import find_preview, scan_library, search_library


def _node_names(node) -> list[str]:
    return [s.name for s in node.subdirs]


def test_scan_missing_library(tmp_path: Path) -> None:
    result = scan_library(tmp_path / "nope")
    assert not result.ok
    assert result.errors


def test_scan_empty_library_is_valid(tmp_path: Path) -> None:
    """Launching with an empty library must not crash."""
    empty = tmp_path / "empty library"
    empty.mkdir()
    result = scan_library(empty)
    assert result.ok
    assert result.node is not None
    assert result.node.subdirs == []
    assert result.node.configs == []


def test_scan_file_path_is_not_a_folder(tmp_path: Path) -> None:
    f = tmp_path / "file.json"
    f.write_text("{}", encoding="utf-8")
    result = scan_library(f)
    assert not result.ok
    assert result.errors


def test_scan_categories(library: Path) -> None:
    result = scan_library(library)
    assert result.ok
    node = result.node
    assert node is not None
    names = _node_names(node)
    assert "Charms" in names
    assert "emotes" in names
    assert "FastFlags" in names
    assert "rivals skins" in names
    assert "Texture and skyboxes" in names


def test_flat_category_configs(library: Path) -> None:
    node = scan_library(library).node
    charms = next(s for s in node.subdirs if s.name == "Charms")
    assert len(charms.configs) == 2
    assert all(c.kind == KIND_FILE for c in charms.configs)
    assert {c.name for c in charms.configs} == {
        "nemesis charm",
        "plat 1 seas 2 arch",
    }


def test_weapon_with_multiple_skins_is_navigation(library: Path) -> None:
    node = scan_library(library).node
    skins = next(s for s in node.subdirs if s.name == "rivals skins")
    primary = next(s for s in skins.subdirs if s.name == "Primary")
    assault = next(s for s in primary.subdirs if s.name == "Assault Rifle")
    assert len(assault.configs) == 2
    assert {c.name for c in assault.configs} == {"ak-47", "key up"}


def test_weapon_with_single_skin_is_file_config(library: Path) -> None:
    node = scan_library(library).node
    skins = next(s for s in node.subdirs if s.name == "rivals skins")
    melee = next(s for s in skins.subdirs if s.name == "Melee")
    axe = next(s for s in melee.subdirs if s.name == "Battle Axe")
    assert len(axe.configs) == 1
    config = axe.configs[0]
    assert config.name == "NordicAxe"
    assert config.kind == KIND_FILE


def test_dependency_mesh_detected(library: Path) -> None:
    node = scan_library(library).node
    skins = next(s for s in node.subdirs if s.name == "rivals skins")
    secondary = next(s for s in skins.subdirs if s.name == "Secondary")
    gun = next(s for s in secondary.subdirs if s.name == "Hand gun")
    pixel = next(c for c in gun.configs if c.name == "Pixelhandgun")
    names = {f.name for f in pixel.files}
    assert "Pixelhandgun.json" in names
    assert "Pixelboddy.obj" in names  # referenced by the JSON
    # The other mesh is not referenced by this JSON.
    assert "pxl mag.obj" not in names


def test_pack_folder_with_preview_is_folder_config(library: Path) -> None:
    node = scan_library(library).node
    textures = next(s for s in node.subdirs if s.name == "Texture and skyboxes")
    # A folder with one JSON + companion files is a single folder config.
    config = next(c for c in textures.configs if c.name == "Texture packs")
    assert config.kind == KIND_FOLDER
    assert config.name == "Texture packs"
    assert config.preview is not None
    assert config.preview.name == "preview.png"
    assert len(config.files) == 2  # json + preview


def test_sky_pack_multiple_jsons_navigation(library: Path) -> None:
    node = scan_library(library).node
    textures = next(s for s in node.subdirs if s.name == "Texture and skyboxes")
    sky = next(s for s in textures.subdirs if s.name == "Sky")
    assert len(sky.configs) == 2
    assert {c.name for c in sky.configs} == {"cloudly sky", "pink sky"}


def test_preview_priority(tmp_path: Path) -> None:
    folder = tmp_path / "Weapon X"
    folder.mkdir()
    (folder / "cover.jpg").write_bytes(b"jpeg")
    (folder / "preview.png").write_bytes(b"png")
    (folder / "random.png").write_bytes(b"png")
    assert find_preview(folder) is not None
    assert find_preview(folder).name == "preview.png"


def test_preview_single_image(tmp_path: Path) -> None:
    folder = tmp_path / "Solo"
    folder.mkdir()
    (folder / "my_art.jpg").write_bytes(b"jpeg")
    assert find_preview(folder).name == "my_art.jpg"


def test_preview_none(tmp_path: Path) -> None:
    folder = tmp_path / "Empty"
    folder.mkdir()
    assert find_preview(folder) is None


def test_search_matches_ancestors(library: Path) -> None:
    node = scan_library(library).node
    # "sniper" style query: matches a weapon name anywhere in the path.
    results = search_library(node, "assault")
    assert len(results) == 2
    assert {r.name for r in results} == {"ak-47", "key up"}

    results = search_library(node, "hand gun")
    assert len(results) == 2


def test_search_empty_and_missing(library: Path) -> None:
    node = scan_library(library).node
    assert search_library(node, "   ") == []
    assert search_library(node, "zzzzz") == []


def test_image_sidecar_is_not_a_config(tmp_path: Path) -> None:
    """A ``.image.json`` sidecar must never become a configuration."""
    from tests.conftest import write_json

    root = tmp_path / "lib"
    charms = root / "Charms"
    write_json(charms / "Rival Skin.json", {"replacement_rules": []})
    write_json(charms / "Rival Skin.image.json", {"type": "local", "source": "x", "local_path": "y"})

    node = scan_library(root).node
    charms_node = next(s for s in node.subdirs if s.name == "Charms")
    assert [c.name for c in charms_node.configs] == ["Rival Skin"]


def test_image_sidecar_invisible_in_single_json_folder(tmp_path: Path) -> None:
    """A JSON + its sidecar stays a pure-JSON navigation folder (one config)."""
    from tests.conftest import write_json

    root = tmp_path / "lib"
    weapon = root / "rivals skins" / "Melee" / "energy rifle"
    write_json(weapon / "voidrifle.json", {"replacement_rules": []})
    write_json(weapon / "voidrifle.image.json", {"type": "local", "source": "x", "local_path": "y"})

    node = scan_library(root).node
    skins = next(s for s in node.subdirs if s.name == "rivals skins")
    melee = next(s for s in skins.subdirs if s.name == "Melee")
    rifle = next(s for s in melee.subdirs if s.name == "energy rifle")
    assert [c.name for c in rifle.configs] == ["voidrifle"]


def test_image_sidecar_excluded_from_folder_config(tmp_path: Path) -> None:
    """A folder config's image.json is not copied with the configuration."""
    from tests.conftest import write_json

    root = tmp_path / "lib"
    pack = root / "Texture packs"
    write_json(pack / "config.json", {"replacement_rules": []})
    (pack / "preview.png").write_bytes(b"png")
    write_json(pack / "image.json", {"type": "local", "source": "x", "local_path": "y"})

    node = scan_library(root).node
    config = node.configs[0]
    assert config.kind == KIND_FOLDER
    names = {f.name for f in config.files}
    assert names == {"config.json", "preview.png"}
    assert "image.json" not in names


def test_scanner_applies_metadata_preview(tmp_path: Path, monkeypatch) -> None:
    """After saving a sidecar, a scan resolves the card preview to the cache image."""
    from app.config import data_dir
    from app.image_manager import ImageManager
    from tests.conftest import write_json

    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))

    root = tmp_path / "lib"
    write_json(root / "Charms" / "Rival Skin.json", {"replacement_rules": []})

    result = scan_library(root)
    charms = next(s for s in result.node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "Rival Skin")
    assert item.preview is None  # no library preview yet

    cache_img = data_dir() / "image_cache" / "test.png"
    cache_img.parent.mkdir(parents=True, exist_ok=True)
    cache_img.write_bytes(b"png")
    manager = ImageManager(cache_img.parent)
    manager.save_downloaded(item, "https://x/y.png", cache_img)

    result = scan_library(root)
    charms = next(s for s in result.node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "Rival Skin")
    assert item.preview == cache_img
