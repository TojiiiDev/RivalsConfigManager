"""Tests for the Editor Mode.

Covers the core integration logic (:mod:`app.editor`) and the Editor Mode
view (:mod:`ui.views.editor_view`): add/replace/remove a preview, real
integration into ``assets/`` + ``manifest.json``, no PC-path dependency,
restart/language persistence, invalid-image refusal, and the admin gate.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from PySide6.QtCore import Qt

from app.editor import (
    EditorManager,
    EditorResult,
    asset_key_for,
    load_project_manifest,
)
from app.image_metadata import effective_preview, load_metadata, local_image_path
from app.i18n import t
from app.models import KIND_FILE, ConfigItem, Node

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)
def _make_jpeg(path: Path) -> Path:
    """A valid 1x1 JPEG written through Qt (no hand-rolled magic bytes)."""
    from PySide6.QtGui import QImage

    img = QImage(1, 1, QImage.Format_RGB32)
    img.fill(0xFF0000)
    assert img.save(str(path), "JPG")
    return path


def _make_png(path: Path, color: int = 0xFF0000) -> Path:
    """A valid 1x1 PNG written through Qt (guaranteed decodable)."""
    from PySide6.QtGui import QImage

    img = QImage(1, 1, QImage.Format_RGB32)
    img.fill(color)
    assert img.save(str(path), "PNG")
    return path


def _file_config(root: Path, *parts: str) -> ConfigItem:
    path = root.joinpath(*parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    return ConfigItem(name=path.stem, path=path, kind=KIND_FILE, files=[path], json_files=[path])


def _folder_node(root: Path, *parts: str) -> Node:
    path = root.joinpath(*parts)
    path.mkdir(parents=True, exist_ok=True)
    return Node(name=path.name, path=path)


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    (project / "assets").mkdir(parents=True, exist_ok=True)
    return project


@pytest.fixture(autouse=True)
def _appdata(tmp_path: Path, monkeypatch) -> Path:
    appdata = tmp_path / "AppData"
    appdata.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    return appdata


@pytest.fixture(autouse=True)
def _isolated_project_root(tmp_path: Path, monkeypatch) -> None:
    """Never let an EditorManager touch the real repository in tests: the
    default project root is redirected to a temp directory."""
    import app.editor as editor_mod

    monkeypatch.setattr(
        editor_mod, "default_project_root", lambda: tmp_path / "default-project"
    )


# ---------------------------------------------------------------------- #
# asset_key_for — stable identity, never the displayed name
# ---------------------------------------------------------------------- #
def test_asset_key_for_file_config_is_slug_chain(tmp_path: Path) -> None:
    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    item = _file_config(lib, "rivals skins", "Primary", "Assault Rifle", "ak-47.json")
    assert asset_key_for(item, root) == "rivals_skins/primary/assault_rifle/ak_47"


def test_asset_key_for_folder_node_is_slug_chain(tmp_path: Path) -> None:
    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    node = _folder_node(lib, "rivals skins", "Melee", "Battle Axe")
    assert asset_key_for(node, root) == "rivals_skins/melee/battle_axe"


def test_asset_key_for_flat_config(tmp_path: Path) -> None:
    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    item = _file_config(lib, "Charms", "nemesis charm.json")
    assert asset_key_for(item, root) == "charms/nemesis_charm"


def test_asset_key_disambiguates_same_name_by_chain(tmp_path: Path) -> None:
    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    a = _file_config(lib, "rivals skins", "Secondary", "Hand gun", "hand gun.json")
    b = _file_config(lib, "rivals skins", "Secondary", "Revolver", "hand gun.json")
    assert asset_key_for(a, root) != asset_key_for(b, root)


# ---------------------------------------------------------------------- #
# Integrate — add a preview, real project resource, no PC path
# ---------------------------------------------------------------------- #
def test_integrate_adds_preview_and_publishes_resource(tmp_path: Path) -> None:
    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    item = _file_config(lib, "rivals skins", "Primary", "Assault Rifle", "ak-47.json")
    project = _project(tmp_path)
    source = tmp_path / "AK.png"
    source.write_bytes(PNG_1PX)

    manager = EditorManager(library_root=root, project_root=project)
    result = manager.integrate(item, source)

    assert result.ok
    assert result.preview is not None and result.preview.is_file()
    assert result.project_integrated
    assert result.asset_key == "rivals_skins/primary/assault_rifle/ak_47"

    # Real project resource: file + manifest entry with sha256/size/version.
    asset = project / "assets" / "rivals_skins" / "primary" / "assault_rifle" / "ak_47.png"
    assert asset.is_file()
    manifest = load_project_manifest(project)
    entry = manifest["assets"][result.asset_key]
    assert entry["path"] == "assets/rivals_skins/primary/assault_rifle/ak_47.png"
    assert entry["version"] == 1
    assert entry["size"] == len(PNG_1PX)
    assert manifest["assets_version"]

    # Local association: sidecar + cached copy, and NO personal PC path.
    meta = load_metadata(item)
    assert meta["type"] == "local"
    assert "source" not in meta
    assert meta["local_path"].startswith("image_cache/")
    assert local_image_path(item) == result.preview


def test_integrate_updates_card_preview(tmp_path: Path) -> None:
    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    item = _file_config(lib, "Charms", "nemesis charm.json")
    project = _project(tmp_path)
    source = tmp_path / "charm.png"
    source.write_bytes(PNG_1PX)

    assert effective_preview(item) is None  # no preview yet
    manager = EditorManager(library_root=root, project_root=project)
    manager.integrate(item, source)

    resolved = effective_preview(item)
    assert resolved is not None and resolved.is_file()


def test_integrate_does_not_depend_on_pc_source(tmp_path: Path) -> None:
    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    item = _file_config(lib, "emotes", "flossswap.json")
    project = _project(tmp_path)
    source = tmp_path / "emo.png"
    source.write_bytes(PNG_1PX)

    manager = EditorManager(library_root=root, project_root=project)
    result = manager.integrate(item, source)

    # The original file disappears — the app keeps its own copy.
    source.unlink()
    assert result.preview.is_file()
    assert local_image_path(item) == result.preview
    assert effective_preview(item) == result.preview


def test_preview_survives_restart_and_language_change(tmp_path: Path, monkeypatch) -> None:
    from app.i18n import current_language, set_language

    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    path = lib / "rivals skins" / "Primary" / "Bow" / "longbow.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    project = _project(tmp_path)
    source = tmp_path / "bow.png"
    source.write_bytes(PNG_1PX)

    manager = EditorManager(library_root=root, project_root=project)
    result = manager.integrate(
        ConfigItem(name=path.stem, path=path, kind=KIND_FILE), source
    )

    # Restart simulation: a freshly scanned item resolves the same preview.
    fresh = ConfigItem(name=path.stem, path=path, kind=KIND_FILE)
    assert local_image_path(fresh) == result.preview

    # Language change never changes the association (path-based identity).
    previous = current_language()
    try:
        set_language("fr")
        assert effective_preview(fresh) == result.preview
        set_language("en")
        assert effective_preview(fresh) == result.preview
    finally:
        set_language(previous)


def test_multiple_elements_have_distinct_previews(tmp_path: Path) -> None:
    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    a = _file_config(lib, "Charms", "charm a.json")
    b = _file_config(lib, "Charms", "charm b.json")
    project = _project(tmp_path)
    src_a = _make_png(tmp_path / "a.png", 0xFF0000)
    src_b = _make_png(tmp_path / "b.png", 0x0000FF)

    manager = EditorManager(library_root=root, project_root=project)
    ra = manager.integrate(a, src_a)
    rb = manager.integrate(b, src_b)

    assert ra.preview != rb.preview
    assert ra.asset_key != rb.asset_key
    assert ra.preview.read_bytes() == src_a.read_bytes()
    assert rb.preview.read_bytes() == src_b.read_bytes()
    assert ra.preview.read_bytes() != rb.preview.read_bytes()
    manifest = load_project_manifest(project)
    assert len(manifest["assets"]) == 2


# ---------------------------------------------------------------------- #
# Replace — version bump, no duplicate accumulation
# ---------------------------------------------------------------------- #
def test_replace_same_extension_bumps_version_without_duplicates(tmp_path: Path) -> None:
    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    item = _file_config(lib, "rivals skins", "Primary", "Assault Rifle", "ak-47.json")
    project = _project(tmp_path)
    src_a = _make_png(tmp_path / "a.png", 0xFF0000)
    src_b = _make_png(tmp_path / "b.png", 0x0000FF)

    manager = EditorManager(library_root=root, project_root=project)
    manager.integrate(item, src_a)
    manager.integrate(item, src_b)

    manifest = load_project_manifest(project)
    entry = manifest["assets"]["rivals_skins/primary/assault_rifle/ak_47"]
    assert entry["version"] == 2
    assert entry["path"] == "assets/rivals_skins/primary/assault_rifle/ak_47.png"

    # Only ONE file for this key (no ak_47_1.png, ak_47_2.png, ...).
    folder = project / "assets" / "rivals_skins" / "primary" / "assault_rifle"
    assert [p.name for p in folder.iterdir()] == ["ak_47.png"]
    assert (folder / "ak_47.png").read_bytes() == src_b.read_bytes()


def test_replace_with_different_extension_removes_old_file(tmp_path: Path) -> None:
    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    item = _file_config(lib, "Charms", "nemesis charm.json")
    project = _project(tmp_path)
    src_png = tmp_path / "a.png"
    src_png.write_bytes(PNG_1PX)
    src_jpg = tmp_path / "b.jpg"
    _make_jpeg(src_jpg)

    manager = EditorManager(library_root=root, project_root=project)
    manager.integrate(item, src_png)
    manager.integrate(item, src_jpg)

    folder = project / "assets" / "charms"
    names = [p.name for p in folder.iterdir()]
    assert names == ["nemesis_charm.jpg"]
    manifest = load_project_manifest(project)
    entry = manifest["assets"]["charms/nemesis_charm"]
    assert entry["path"] == "assets/charms/nemesis_charm.jpg"
    assert entry["version"] == 2


# ---------------------------------------------------------------------- #
# Remove — clean removal of local + project resources
# ---------------------------------------------------------------------- #
def test_remove_deletes_sidecar_cache_and_project_asset(tmp_path: Path) -> None:
    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    item = _file_config(lib, "Charms", "nemesis charm.json")
    project = _project(tmp_path)
    source = tmp_path / "a.png"
    source.write_bytes(PNG_1PX)

    manager = EditorManager(library_root=root, project_root=project)
    result = manager.integrate(item, source)
    cached = result.preview

    manager.remove(item)

    assert not cached.exists()
    assert load_metadata(item) is None
    assert not (project / "assets" / "charms" / "nemesis_charm.png").exists()
    assert "charms/nemesis_charm" not in load_project_manifest(project)["assets"]


def test_remove_without_image_is_noop(tmp_path: Path) -> None:
    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    item = _file_config(lib, "Charms", "ghost.json")
    project = _project(tmp_path)
    manager = EditorManager(library_root=root, project_root=project)
    result = manager.remove(item)
    assert result.ok
    assert (lib / "Charms" / "ghost.json").exists()


# ---------------------------------------------------------------------- #
# Invalid images are refused cleanly
# ---------------------------------------------------------------------- #
def test_integrate_rejects_wrong_format(tmp_path: Path) -> None:
    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    item = _file_config(lib, "Charms", "nemesis charm.json")
    project = _project(tmp_path)
    source = tmp_path / "notes.txt"
    source.write_text("not an image", encoding="utf-8")

    manager = EditorManager(library_root=root, project_root=project)
    result = manager.integrate(item, source)

    assert not result.ok
    assert result.preview is None
    assert result.error
    assert load_metadata(item) is None
    assert load_project_manifest(project)["assets"] == {}


def test_integrate_rejects_corrupt_image(tmp_path: Path) -> None:
    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    item = _file_config(lib, "Charms", "nemesis charm.json")
    project = _project(tmp_path)
    source = tmp_path / "fake.png"
    source.write_bytes(b"not really a png")

    manager = EditorManager(library_root=root, project_root=project)
    result = manager.integrate(item, source)
    assert not result.ok
    assert result.preview is None
    assert load_project_manifest(project)["assets"] == {}


# ---------------------------------------------------------------------- #
# Project unavailable (frozen) -> still associates locally
# ---------------------------------------------------------------------- #
def test_frozen_build_associates_locally_without_publishing(tmp_path: Path, monkeypatch) -> None:
    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    item = _file_config(lib, "Charms", "nemesis charm.json")
    source = tmp_path / "a.png"
    source.write_bytes(PNG_1PX)

    import app.editor as editor_mod

    monkeypatch.setattr(editor_mod, "default_project_root", lambda: None)
    manager = EditorManager(library_root=root)
    result = manager.integrate(item, source)

    assert result.ok
    assert result.preview is not None and result.preview.is_file()
    assert not result.project_integrated
    assert result.error  # a soft note, not a failure


# ---------------------------------------------------------------------- #
# Admin gate (env var) + Editor Mode view
# ---------------------------------------------------------------------- #
def test_admin_enabled_via_env_var(monkeypatch) -> None:
    import app.config as config_mod

    monkeypatch.delenv("RCM_ADMIN_MODE", raising=False)
    assert config_mod.admin_enabled() is False
    monkeypatch.setenv("RCM_ADMIN_MODE", "1")
    assert config_mod.admin_enabled() is True


@pytest.fixture()
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_editor_view_lists_and_emits(qapp, tmp_path: Path) -> None:
    from ui.views.editor_view import EditorView

    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    a = _file_config(lib, "Charms", "charm a.json")
    b = _folder_node(lib, "rivals skins")
    root.configs.append(a)
    root.subdirs.append(b)

    view = EditorView()
    view.set_library(root)
    assert view._list.count() == 2

    # Select the config item (index 1 — subdirs come first in the list).
    cfg_item = view._list.item(1)
    assert cfg_item is not None
    assert isinstance(cfg_item.data(Qt.UserRole), ConfigItem)
    view._list.setCurrentItem(cfg_item)
    assert view._current is not None

    captured: list = []
    view.integrate_requested.connect(lambda target, src: captured.append((target, src)))
    view._pending_source = Path("C:/fake/source.png")
    view._refresh_detail()
    view._integrate()
    assert captured[0][0] is view._current
    assert Path(captured[0][1]) == Path("C:/fake/source.png")

    # Cancel discards the pending choice and never integrates.
    view._pending_source = Path("C:/fake/source.png")
    view._cancel_pending()
    assert view._pending_source is None
    assert not view._integrate_btn.isVisible()


def test_editor_view_remove_emits(qapp, tmp_path: Path) -> None:
    from ui.views.editor_view import EditorView

    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    cfg = _file_config(lib, "Charms", "charm a.json")
    root.configs.append(cfg)

    view = EditorView()
    view.set_library(root)
    view._list.setCurrentRow(0)

    captured: list = []
    view.remove_requested.connect(lambda target: captured.append(target))
    view._remove()
    assert captured == [cfg]


# ---------------------------------------------------------------------- #
# End-to-end in the main window (admin build)
# ---------------------------------------------------------------------- #
def test_editor_mode_end_to_end_in_main_window(qapp, tmp_path: Path, monkeypatch) -> None:
    import app.editor as editor_mod
    from app.scanner import find_config
    from ui.main_window import PAGE_EDITOR, MainWindow

    monkeypatch.setenv("RCM_ADMIN_MODE", "1")
    project = tmp_path / "project"
    (project / "assets").mkdir(parents=True)
    monkeypatch.setattr(editor_mod, "default_project_root", lambda: project)

    lib = tmp_path / "Rivals configs"
    charm_path = lib / "Charms" / "nemesis charm.json"
    charm_path.parent.mkdir(parents=True, exist_ok=True)
    charm_path.write_text("{}", encoding="utf-8")
    fleasion = tmp_path / "fleasion"
    fleasion.mkdir(parents=True, exist_ok=True)
    (fleasion / "settings.json").write_text("{}", encoding="utf-8")

    settings_path = tmp_path / "AppData" / "RivalsConfigManager" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(
            {"library_dir": str(lib), "fleasion_dir": str(fleasion), "language": "fr"}
        ),
        encoding="utf-8",
    )

    window = MainWindow()
    window.show()
    qapp.processEvents()
    try:
        # The discreet editor button is visible in an admin build.
        assert window._editor_btn.isVisible()

        window.go((PAGE_EDITOR, None))
        qapp.processEvents()
        assert window._editor_view._list.count() >= 1

        target = find_config(window.root_node, charm_path)
        assert target is not None
        source = tmp_path / "charm.png"
        source.write_bytes(PNG_1PX)

        window._editor_integrate(target, str(source))
        qapp.processEvents()

        # Real project resource published (assets/ + manifest.json).
        assert (project / "assets" / "charms" / "nemesis_charm.png").is_file()
        assert "charms/nemesis_charm" in load_project_manifest(project)["assets"]

        # The card now has a preview (re-scanned tree).
        refreshed = find_config(window.root_node, charm_path)
        assert refreshed is not None and refreshed.preview is not None
        assert refreshed.preview.is_file()
    finally:
        window.close()
        window.deleteLater()
        qapp.processEvents()


# ---------------------------------------------------------------------- #
# Category (Node) selection — detail panel shows for all item types
# ---------------------------------------------------------------------- #
def test_category_node_is_selectable_and_shows_detail(qapp, tmp_path: Path) -> None:
    """Selecting a category (Node) must display its info in the detail panel
    with an active Add/Replace button."""
    from ui.views.editor_view import EditorView

    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    cat = _folder_node(lib, "Charms")
    root.subdirs.append(cat)

    view = EditorView()
    view.set_library(root)
    assert view._list.count() == 1

    # Single-click selects the category.
    item = view._list.item(0)
    view._list.setCurrentItem(item)
    assert view._current is not None
    assert isinstance(view._current, Node)
    assert view._current.name == "Charms"

    # Detail panel is active with the correct type label.
    assert view._detail_name.text() == "Charms"
    assert t("editor.item_type_folder") in view._detail_type.text()

    # Add/Replace is active (no preview yet).
    assert view._add_replace_btn.isEnabled()
    assert not view._remove_btn.isVisibleTo(view)


def test_category_with_preview_shows_remove(qapp, tmp_path: Path) -> None:
    """A category that already has a preview must show Remove Preview."""
    from ui.views.editor_view import EditorView

    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    cat = Node(name="Textures", path=lib / "Textures", preview=tmp_path / "tex.png")
    root.subdirs.append(cat)

    view = EditorView()
    view.set_library(root)
    view._list.setCurrentRow(0)

    assert view._current is not None
    assert view._current.preview is not None
    assert view._remove_btn.isVisibleTo(view)
    assert view._add_replace_btn.isEnabled()


# ---------------------------------------------------------------------- #
# Single-element auto-select — detail panel shows immediately
# ---------------------------------------------------------------------- #
def test_single_element_auto_selected_and_detail_visible(qapp, tmp_path: Path) -> None:
    """When a folder contains only one item, it must be auto-selected and
    the detail panel must show immediately without a second click."""
    from ui.views.editor_view import EditorView

    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    # One folder, one config inside — total of one visible element.
    only = _file_config(lib, "Charms", "only_item.json")
    root.configs.append(only)

    view = EditorView()
    view.set_library(root)

    # The single config must be auto-selected.
    assert view._list.count() == 1
    assert view._current is not None
    assert isinstance(view._current, ConfigItem)
    assert view._current.name == "only_item"
    assert view._detail_name.text() == "only_item"
    assert view._add_replace_btn.isEnabled()


def test_single_folder_auto_selected_in_nested_level(qapp, tmp_path: Path) -> None:
    """When navigating into a folder with a single sub-folder, that
    sub-folder must be auto-selected and the detail panel must appear."""
    from ui.views.editor_view import EditorView

    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    parent = _folder_node(lib, "Utility")
    single_child = _folder_node(lib, "Spider Web")
    parent.subdirs.append(single_child)
    root.subdirs.append(parent)

    view = EditorView()
    view.set_library(root)

    # Navigate into Utility (one child: Spider Web).
    view._enter_folder(parent)
    assert view._list.count() == 1
    assert view._current is not None
    assert view._current.name == "Spider Web"
    assert t("editor.item_type_folder") in view._detail_type.text()
    assert view._add_replace_btn.isEnabled()


def test_single_skin_auto_selected_and_editable(qapp, tmp_path: Path) -> None:
    """When an arme has a single skin, the skin must be auto-selected
    and immediately editable in the detail panel."""
    from ui.views.editor_view import EditorView

    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    weapon = _folder_node(lib, "rivals skins", "Primary", "AK")
    skin = _file_config(lib, "rivals skins", "Primary", "AK", "default.json")
    weapon.configs.append(skin)
    # Wire the parent chain.
    primary = weapon.path.parent
    primary_node = Node(name="Primary", path=primary)
    primary_node.subdirs.append(weapon)
    root.subdirs.append(primary_node)

    view = EditorView()
    view.set_library(root)
    view._enter_folder(primary_node)
    view._enter_folder(weapon)

    assert view._list.count() == 1
    assert view._current is not None
    assert view._current.name == "default"
    assert view._add_replace_btn.isEnabled()


# ---------------------------------------------------------------------- #
# Node vs ConfigItem type label in detail panel
# ---------------------------------------------------------------------- #
def test_detail_panel_shows_correct_type_label(qapp, tmp_path: Path) -> None:
    """The detail panel type label must match the actual item type."""
    from ui.views.editor_view import EditorView

    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    folder = _folder_node(lib, "Skyboxes")
    root.subdirs.append(folder)
    cfg = _file_config(lib, "Charms", "charm.json")
    root.configs.append(cfg)

    view = EditorView()
    view.set_library(root)

    # Select the folder.
    view._list.setCurrentRow(0)
    assert view._detail_type.text() == t("editor.item_type_folder")

    # Select the config.
    view._list.setCurrentRow(1)
    assert view._detail_type.text() == t("editor.item_type_config")


# ---------------------------------------------------------------------- #
# Multi-element lists still work (regression)
# ---------------------------------------------------------------------- #
def test_multi_element_list_selection_still_works(qapp, tmp_path: Path) -> None:
    """A list with multiple elements: clicking each one updates the detail
    panel correctly."""
    from ui.views.editor_view import EditorView

    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    a = _folder_node(lib, "Category A")
    b = _file_config(lib, "Charms", "charm b.json")
    c = _folder_node(lib, "Category C")
    root.subdirs.extend([a, c])
    root.configs.append(b)

    view = EditorView()
    view.set_library(root)
    assert view._list.count() == 3

    # Select each item and verify the detail panel updates.
    # List order: subdirs first (A, C), then configs (charm b).
    for idx, expected_name in enumerate(["Category A", "Category C", "charm b"]):
        view._list.setCurrentRow(idx)
        assert view._current is not None
        assert view._current.name == expected_name
        assert view._detail_name.text() == expected_name


def test_node_integrate_and_remove(qapp, tmp_path: Path) -> None:
    """Integration and removal must work for a Node (category) target."""
    from ui.views.editor_view import EditorView

    lib = tmp_path / "Rivals configs"
    root = Node(name="Rivals configs", path=lib)
    cat = _folder_node(lib, "Textures")
    root.subdirs.append(cat)

    view = EditorView()
    view.set_library(root)
    view._list.setCurrentRow(0)
    assert view._current is not None

    # Simulate adding a preview.
    captured: list = []
    view.integrate_requested.connect(lambda t, s: captured.append((t, s)))
    view._pending_source = Path("C:/fake/tex.png")
    view._refresh_detail()
    view._integrate()
    assert captured[0][0] is view._current
    assert Path(captured[0][1]) == Path("C:/fake/tex.png")

    # Simulate removing a preview.
    captured2: list = []
    view.remove_requested.connect(lambda t: captured2.append(t))
    view._remove()
    assert captured2[0] is view._current
