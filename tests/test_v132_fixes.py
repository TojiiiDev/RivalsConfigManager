"""v1.3.2 regression tests.

Covers the fixes requested for the finalisation release:

* progressive tree navigation (Catégorie → Arme → Skin) with a real
  Level 3 listing the configurations inside the chosen weapon;
* building a profile through that tree (ProfileDialog « Parcourir… »);
* custom theme: the colour swatches really open a ``QColorDialog`` and the
  chosen colour is stored + applied + persisted;
* Favorites: the star toggles, the config appears in the virtual Favorites
  page, un-favouriting removes the card but never the file;
* search results carry the same preview images as normal cards;
* no false MP3 requirement for a config that does not explicitly reference
  an audio file (absence is never proof of a requirement).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QDialog


# ---------------------------------------------------------------------- #
# Fixtures
# ---------------------------------------------------------------------- #
@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _configure(appdata: Path, library: Path, fleasion: Path) -> None:
    """Write the settings.json the app reads on startup (like test_smoke)."""
    settings_path = appdata / "RivalsConfigManager" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(
            {
                "library_dir": str(library),
                "fleasion_dir": str(fleasion),
            }
        ),
        encoding="utf-8",
    )
    fleasion.mkdir(parents=True, exist_ok=True)
    (fleasion / "settings.json").write_text("{}", encoding="utf-8")


def _tree_library(root: Path) -> Path:
    """A library with a real nested category (rivals skins/primary/AK)."""
    lib = root / "lib"
    (lib / "rivals skins" / "primary" / "AK").mkdir(parents=True)
    (lib / "rivals skins" / "primary" / "AK" / "Skin 1.json").write_text(
        '{"replacement_rules": []}', encoding="utf-8"
    )
    (lib / "rivals skins" / "primary" / "AK" / "Skin 2.json").write_text(
        '{"replacement_rules": []}', encoding="utf-8"
    )
    (lib / "rivals skins" / "Secondary").mkdir(parents=True)
    (lib / "Charms").mkdir()
    return lib


# ---------------------------------------------------------------------- #
# 1. Tree navigation: Catégorie → Arme → Skin (Level 3)
# ---------------------------------------------------------------------- #
def test_tree_navigation_level3_lists_skins(tmp_path: Path, qapp) -> None:
    from ui.views.destination_picker import DestinationPickerDialog

    lib = _tree_library(tmp_path)
    dialog = DestinationPickerDialog(lib, pick_config=True)

    primary_item = next(
        dialog._category_list.item(i)
        for i in range(dialog._category_list.count())
        if dialog._category_list.item(i).data(0x0100)[0] == "primary"
    )
    dialog._on_category_clicked(primary_item)
    ak_idx = next(
        i
        for i in range(dialog._weapon_list.count())
        if dialog._weapon_list.item(i).data(0x0100) == "AK"
    )
    dialog._weapon_list.setCurrentRow(ak_idx)
    dialog._weapon = "AK"
    dialog._show_step(2)

    names = [
        dialog._configs_list.item(i).text()
        for i in range(dialog._configs_list.count())
    ]
    assert "Skin 1" in names and "Skin 2" in names

    # Selecting a skin resolves the destination to its real folder.
    for i in range(dialog._configs_list.count()):
        if dialog._configs_list.item(i).text() == "Skin 2":
            dialog._configs_list.setCurrentRow(i)
            dialog._on_config_clicked(dialog._configs_list.item(i))
            break
    dialog._show_step(3)
    assert dialog.selected_config is not None
    assert dialog.selected_config.name == "Skin 2"
    assert dialog.destination == lib / "rivals skins" / "primary" / "AK"
    dialog.deleteLater()


def test_tree_navigation_new_weapon_skips_configs(tmp_path: Path, qapp) -> None:
    """A brand-new weapon (no folder yet) skips Level 3: straight to confirm."""
    from ui.views.destination_picker import DestinationPickerDialog

    lib = _tree_library(tmp_path)
    dialog = DestinationPickerDialog(lib)
    primary_item = next(
        dialog._category_list.item(i)
        for i in range(dialog._category_list.count())
        if dialog._category_list.item(i).data(0x0100)[0] == "primary"
    )
    dialog._category_list.setCurrentItem(primary_item)
    dialog._go_next()  # category -> weapon page
    dialog._new_weapon.setText("Railgun")
    dialog._go_next()  # weapon page -> no folder -> confirm
    assert dialog._stack.currentIndex() == 3
    assert dialog.destination == lib / "rivals skins" / "primary" / "Railgun"
    dialog.deleteLater()


# ---------------------------------------------------------------------- #
# 2. Build a profile through the tree (ProfileDialog « Parcourir… »)
# ---------------------------------------------------------------------- #
def test_profile_built_through_tree_navigation(tmp_path: Path, qapp) -> None:
    from app.models import ConfigItem
    from ui.views.destination_picker import DestinationPickerDialog
    from ui.views.profile_dialog import ProfileDialog

    lib = _tree_library(tmp_path)
    configs = [
        ConfigItem(
            name="Skin 1",
            path=lib / "rivals skins" / "primary" / "AK" / "Skin 1.json",
            kind="file",
        ),
        ConfigItem(
            name="Skin 2",
            path=lib / "rivals skins" / "primary" / "AK" / "Skin 2.json",
            kind="file",
        ),
    ]
    dialog = ProfileDialog(lib, configs)
    assert not dialog._browse_btn.isHidden()

    def fake_exec(self):
        primary_item = next(
            self._category_list.item(i)
            for i in range(self._category_list.count())
            if self._category_list.item(i).data(0x0100)[0] == "primary"
        )
        self._on_category_clicked(primary_item)
        ak_idx = next(
            i
            for i in range(self._weapon_list.count())
            if self._weapon_list.item(i).data(0x0100) == "AK"
        )
        self._weapon_list.setCurrentRow(ak_idx)
        self._weapon = "AK"
        self._show_step(2)
        for i in range(self._configs_list.count()):
            if self._configs_list.item(i).text() == "Skin 2":
                self._configs_list.setCurrentRow(i)
                self._on_config_clicked(self._configs_list.item(i))
                break
        return QDialog.Accepted

    orig = DestinationPickerDialog.exec
    DestinationPickerDialog.exec = fake_exec  # type: ignore[method-assign]
    try:
        dialog._on_browse()
    finally:
        DestinationPickerDialog.exec = orig  # type: ignore[method-assign]

    checked = [
        dialog._list.item(i).text()
        for i in range(dialog._list.count())
        if dialog._list.item(i).checkState().value == 2  # Qt.Checked
    ]
    assert "Skin 2" in checked
    profile = dialog.result_profile()
    profile.name = "Tryhard"
    assert any(e.name == "Skin 2" for e in profile.entries)
    dialog.deleteLater()


# ---------------------------------------------------------------------- #
# 3. Custom theme: real QColorDialog + apply + persist
# ---------------------------------------------------------------------- #
def test_custom_theme_swatch_opens_color_dialog_and_applies(
    tmp_path: Path, qapp, monkeypatch
) -> None:
    from app.themes import custom_theme_spec
    from ui.views.settings_view import SettingsView

    view = SettingsView()
    # The user selects « Personnalisé » in the theme combo (the real flow);
    # the palette defaults are populated by set_theme_value like the main
    # window does on page render.
    view.set_theme_value("custom")
    custom_index = view._theme_combo.findData("custom")
    view._theme_combo.setCurrentIndex(custom_index)
    assert view._custom_box.isVisibleTo(view)

    picked: list[QColor] = []

    def fake_get_color(initial, parent=None, title=""):
        color = QColor("#00cc00")
        picked.append(color)
        return color

    monkeypatch.setattr("PySide6.QtWidgets.QColorDialog.getColor", staticmethod(fake_get_color))
    view._pick_color("primary")
    assert picked, "clicking the swatch must open a real color dialog"
    assert view._custom_colors.get("primary") == "#00cc00"
    assert "00cc00" in view._custom_buttons["primary"].styleSheet()

    # The emitted theme payload carries the new colour and produces a spec
    # whose accent actually uses it.
    emitted: list[tuple[str, dict]] = []
    view.theme_changed.connect(lambda k, c: emitted.append((k, dict(c))))
    view._pick_color("background")
    assert emitted and emitted[-1][0] == "custom"
    palette = emitted[-1][1]
    spec = custom_theme_spec(
        palette["primary"],
        palette["secondary"],
        palette["accent"],
        palette["background"],
    )
    assert spec.bg.lower() == "#00cc00"  # « Fond » really drives the base
    view.deleteLater()


def test_custom_theme_persists_across_restart(tmp_path: Path, qapp, monkeypatch) -> None:
    from app.config import AppSettings

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))

    settings = AppSettings()
    settings.theme = "custom"
    settings.custom_theme = {
        "primary": "#112233",
        "secondary": "#445566",
        "accent": "#00cc00",
        "background": "#0a0a0a",
        "gradient": True,
        "gradient_angle": 135,
    }
    settings.save()

    fresh = AppSettings.load()
    assert fresh.theme == "custom"
    assert fresh.custom_theme["accent"] == "#00cc00"
    assert fresh.custom_theme["gradient"] is True
    assert fresh.custom_theme["gradient_angle"] == 135


# ---------------------------------------------------------------------- #
# 4. Favorites: star toggles, virtual page, file never touched
# ---------------------------------------------------------------------- #
@pytest.fixture
def ui_window(tmp_path: Path, qapp, monkeypatch):
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    lib = _tree_library(tmp_path)
    _configure(appdata, lib, tmp_path / "fleasion")
    window = MainWindow()
    window.show()
    qapp.processEvents()
    yield window
    window.deleteLater()


def test_favorite_appears_in_favorites_view_and_unfavorite_keeps_file(
    ui_window, qapp
) -> None:
    from app.sync import walk_configs
    from ui.main_window import PAGE_FAVORITES

    target = next(
        c for c in walk_configs(ui_window.root_node) if c.name == "Skin 1"
    )
    ui_window.settings.toggle_favorite(str(target.path))
    ui_window.settings.save()

    ui_window.go((PAGE_FAVORITES, None))
    qapp.processEvents()
    grid = ui_window._favorites_view._grid
    titles = [c._title_label.text() for c in grid._cards]
    assert "Skin 1" in titles
    assert "Skin 2" not in titles

    # The star on the card reflects the state and toggles it.
    card = grid.find_card(str(target.path))
    assert card is not None and card.is_favorite()

    # Un-favouriting removes the card from the page — the file stays.
    ui_window._toggle_favorite(target)
    qapp.processEvents()
    assert len(grid._cards) == 0
    assert target.path.exists()
    assert not ui_window.settings.is_favorite(str(target.path))


def test_favorites_survive_restart(tmp_path: Path, qapp, monkeypatch) -> None:
    from app.sync import walk_configs
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    lib = _tree_library(tmp_path)
    _configure(appdata, lib, tmp_path / "fleasion")

    window = MainWindow()
    window.show()
    qapp.processEvents()
    target = next(
        c for c in walk_configs(window.root_node) if c.name == "Skin 1"
    )
    window.settings.toggle_favorite(str(target.path))
    window.settings.save()
    window.deleteLater()

    fresh = MainWindow()
    fresh.show()
    qapp.processEvents()
    assert str(target.path) in fresh.settings.favorites
    fresh.deleteLater()


# ---------------------------------------------------------------------- #
# 5. Search results carry the same preview images as normal cards
# ---------------------------------------------------------------------- #
def test_search_results_carry_preview_images(tmp_path: Path, qapp, monkeypatch) -> None:
    import base64

    from app.search import SearchState, run_search
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    lib = _tree_library(tmp_path)
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    (lib / "rivals skins" / "primary" / "AK" / "preview.png").write_bytes(png)
    _configure(appdata, lib, tmp_path / "fleasion")

    window = MainWindow()
    window.show()
    qapp.processEvents()
    results = run_search(window.root_node, SearchState(query="Skin"))
    assert results, "search must find the skin"
    for result in results:
        assert result.preview is not None, (
            "search cards must use the same preview as normal cards"
        )
    window.deleteLater()


# ---------------------------------------------------------------------- #
# 6. No false MP3 requirement (absence is never proof of a requirement)
# ---------------------------------------------------------------------- #
def test_no_false_mp3_without_explicit_reference(tmp_path: Path) -> None:
    from app.config_analysis import analyze_config

    folder = tmp_path / "Melee" / "Knife"
    folder.mkdir(parents=True)
    # No audio reference anywhere: only CDN/remote rules and asset ids.
    (folder / "minecraft knife.json").write_text(
        json.dumps(
            {
                "replacement_rules": [
                    {"enabled": True, "mode": "cdn", "cdn_url": "https://cdn.example.com/knife.obj"},
                    {"enabled": True, "mode": "id", "with_id": 18742879471},
                ]
            }
        ),
        encoding="utf-8",
    )
    # An .mp3 sitting in the folder is NOT proof the JSON needs it.
    (folder / "unrelated sound.mp3").write_bytes(b"ID3")
    deps = analyze_config(folder / "minecraft knife.json")
    assert deps.valid
    assert not deps.mp3_required
    assert deps.mp3_files == ()
    assert deps.missing_mp3_files == ()
    assert not deps.obj_required  # the obj reference is a remote URL


def test_mp3_required_only_when_explicitly_referenced(tmp_path: Path) -> None:
    from app.config_analysis import analyze_config

    folder = tmp_path / "Secondary" / "Pistols"
    folder.mkdir(parents=True)
    (folder / "keyrgy.json").write_text(
        json.dumps(
            {
                "replacement_rules": [
                    {"enabled": True, "mode": "local", "local_path": "C:/Sounds/Keylaws sound 1.MP3"},
                ]
            }
        ),
        encoding="utf-8",
    )
    deps = analyze_config(folder / "keyrgy.json")
    assert deps.valid
    assert deps.mp3_required
    assert deps.mp3_files == ("Keylaws sound 1.MP3",)
    assert deps.missing_mp3_files == ("Keylaws sound 1.MP3",)
    # Once the file exists next to the JSON, it is present.
    (folder / "Keylaws sound 1.MP3").write_bytes(b"ID3")
    deps = analyze_config(folder / "keyrgy.json")
    assert deps.present_mp3_files == ("Keylaws sound 1.MP3",)
    assert deps.missing_mp3_files == ()
