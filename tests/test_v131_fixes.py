"""v1.3.1 regression tests — bugs found after real use of v1.3.0.

Covers:

* OBJ/MP3 detection: absence of a file never proves it is required — only
  an explicit reference inside an active ``replacement_rules`` entry counts
  (test_config_analysis.py holds the detailed cases; here the end-to-end
  resolution is re-checked).
* Import destination: a canonical category (Primary…) resolves to its REAL
  folder in the library (``rivals skins/primary``), never to a brand-new
  root-level folder.
* The progressive tree destination picker (categories → weapons → confirm).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from app.categories import (
    destination_categories,
    resolve_category_folder,
)
from app.mod_import import ModAnalysis, ModFile, build_plan
from app.config_analysis import analyze_config, clear_cache
from app.i18n import current_language, set_language


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------------- #
# resolve_category_folder — the real folder, never a guessed root
# ---------------------------------------------------------------------- #
def test_resolve_finds_nested_real_category_folder(tmp_path: Path) -> None:
    """« primary » vit sous « rivals skins » dans la vraie bibliothèque :
    la résolution la trouve (jamais un nouveau « Primary » à la racine)."""
    (tmp_path / "rivals skins" / "primary").mkdir(parents=True)
    (tmp_path / "Charms").mkdir()
    assert resolve_category_folder(tmp_path, "primary") == (
        tmp_path / "rivals skins" / "primary"
    )


def test_resolve_fallback_to_canonical_root_folder(tmp_path: Path) -> None:
    """Aucune catégorie réelle : fallback canonique (le dossier que
    l'installeur crée) — pas de devinette, pas d'erreur."""
    (tmp_path / "Charms").mkdir()
    assert resolve_category_folder(tmp_path, "secondary") is None
    assert resolve_category_folder(tmp_path, "Charms") is None  # non-canonical


def test_resolve_root_level_canonical_folder_is_found(tmp_path: Path) -> None:
    """Une bibliothèque organisée à la racine (Primary, Secondary…) : le
    dossier racine est la catégorie réelle."""
    (tmp_path / "Primary").mkdir()
    (tmp_path / "Primary" / "Assault Rifle").mkdir()
    (tmp_path / "Charms").mkdir()
    assert resolve_category_folder(tmp_path, "primary") == tmp_path / "Primary"


def test_resolve_prefers_real_organization_over_stale_root(tmp_path: Path) -> None:
    """Bibliothèque mixte : un « Primary » racine (créé par l'ancien bug) ET
    le vrai dossier imbriqué « rivals skins/primary » — le dossier réel est
    choisi, le dossier racine parasite est ignoré."""
    (tmp_path / "Primary").mkdir()
    (tmp_path / "rivals skins" / "primary").mkdir(parents=True)
    assert resolve_category_folder(tmp_path, "primary") == (
        tmp_path / "rivals skins" / "primary"
    )


def test_destination_categories_skip_containers_and_are_dynamic(tmp_path: Path) -> None:
    """« rivals skins » (conteneur de catégories) n'apparaît pas comme
    catégorie ; une nouvelle catégorie top-level apparaît automatiquement."""
    (tmp_path / "rivals skins" / "primary").mkdir(parents=True)
    (tmp_path / "Charms").mkdir()
    (tmp_path / "FastFlags").mkdir()
    entries = destination_categories(tmp_path)
    keys = [key for key, _folder in entries]
    assert keys[:4] == ["primary", "secondary", "melee", "utility"]
    assert "rivals skins" not in keys
    assert "Charms" in keys and "FastFlags" in keys
    # primary resolves to its real folder.
    by_key = dict(entries)
    assert by_key["primary"] == tmp_path / "rivals skins" / "primary"
    # Non-canonical categories are their own top-level folder.
    assert by_key["Charms"] == tmp_path / "Charms"


# ---------------------------------------------------------------------- #
# Import destination — the v1.3.1 category bug
# ---------------------------------------------------------------------- #
def _analysis(name: str = "MonSkin") -> ModAnalysis:
    return ModAnalysis(
        name=name, root=Path("."), files=[ModFile("MonSkin.json", 3)], kind="file"
    )


def test_import_plan_uses_real_category_folder(tmp_path: Path) -> None:
    """Choisir « Primary » dans l'import place le mod dans la catégorie
    RÉELLE (rivals skins/primary), jamais dans un nouveau « Primary »
    au niveau racine."""
    (tmp_path / "rivals skins" / "primary" / "Assult Rifle").mkdir(parents=True)
    (tmp_path / "Charms").mkdir()
    plan = build_plan("MonSkin", "primary", "Assult Rifle", _analysis(), tmp_path)
    assert plan.destination == (
        tmp_path / "rivals skins" / "primary" / "Assult Rifle" / "MonSkin"
    )
    assert not (tmp_path / "Primary").exists()


def test_import_plan_fallback_creates_canonical_folder(tmp_path: Path) -> None:
    """Pas de catégorie réelle : l'installeur crée le dossier canonique."""
    (tmp_path / "Charms").mkdir()
    plan = build_plan("MonSkin", "primary", None, _analysis(), tmp_path)
    assert plan.destination == tmp_path / "Primary" / "MonSkin"


def test_import_plan_non_canonical_category_stays_top_level(tmp_path: Path) -> None:
    (tmp_path / "Charms").mkdir()
    plan = build_plan("MonSkin", "Charms", None, _analysis(), tmp_path)
    assert plan.destination == tmp_path / "Charms" / "MonSkin"


# ---------------------------------------------------------------------- #
# Progressive tree destination picker (UI)
# ---------------------------------------------------------------------- #
@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _tree_library(tmp_path: Path) -> Path:
    (tmp_path / "rivals skins" / "primary").mkdir(parents=True)
    (tmp_path / "rivals skins" / "primary" / "Assult Rifle").mkdir()
    (tmp_path / "rivals skins" / "primary" / "Bow").mkdir()
    (tmp_path / "rivals skins" / "Secondary").mkdir(parents=True)
    (tmp_path / "Charms").mkdir()
    return tmp_path


def test_destination_picker_steps_resolve_real_folders(tmp_path: Path, qapp) -> None:
    from ui.views.destination_picker import DestinationPickerDialog

    previous = current_language()
    set_language("fr")  # libellé canonique traduit en français (défaut = en)
    try:
        lib = _tree_library(tmp_path)
        dialog = DestinationPickerDialog(lib)
        # Step 1: canonical categories resolved + real top-level folders, no
        # container « rivals skins ».
        labels = [dialog._category_list.item(i).text()
                  for i in range(dialog._category_list.count())]
        assert "rivals skins" not in labels
        assert "Primaire" in labels
        assert "Charms" in labels
        # Step 2: real weapon folders of the chosen category.
        primary_item = next(
            dialog._category_list.item(i)
            for i in range(dialog._category_list.count())
            if dialog._category_list.item(i).data(0x0100)[0] == "primary"
        )
        dialog._on_category_clicked(primary_item)
        weapons = [
            dialog._weapon_list.item(i).data(0x0100)
            for i in range(dialog._weapon_list.count())
        ]
        assert "Assult Rifle" in weapons and "Bow" in weapons
        assert None in weapons  # « directement dans Primary »
        # Step 3: final destination in the real folder.
        dialog._weapon_list.setCurrentRow(0)
        dialog._weapon = weapons[0]
        dialog._show_step(2)
        assert dialog.destination == lib / "rivals skins" / "primary" / "Assult Rifle"
        dialog.deleteLater()
    finally:
        set_language(previous)


def test_destination_picker_new_weapon_typed(tmp_path: Path, qapp) -> None:
    from ui.views.destination_picker import DestinationPickerDialog

    lib = _tree_library(tmp_path)
    dialog = DestinationPickerDialog(lib)
    primary_item = next(
        dialog._category_list.item(i)
        for i in range(dialog._category_list.count())
        if dialog._category_list.item(i).data(0x0100)[0] == "primary"
    )
    dialog._on_category_clicked(primary_item)
    dialog._new_weapon.setText("Railgun")
    assert dialog.weapon == "Railgun"
    assert dialog.destination == lib / "rivals skins" / "primary" / "Railgun"
    dialog.deleteLater()


def test_destination_picker_will_create_category_falls_back_to_canonical(
    tmp_path: Path, qapp
) -> None:
    from ui.views.destination_picker import DestinationPickerDialog

    (tmp_path / "Charms").mkdir()  # no weapon category exists
    dialog = DestinationPickerDialog(tmp_path)
    melee_item = next(
        dialog._category_list.item(i)
        for i in range(dialog._category_list.count())
        if dialog._category_list.item(i).data(0x0100)[0] == "melee"
    )
    assert melee_item.data(0x0100)[1].endswith("Melee")  # canonical fallback
    dialog._on_category_clicked(melee_item)
    dialog._new_weapon.setText("Katana")
    assert dialog.destination == tmp_path / "Melee" / "Katana"
    dialog.deleteLater()


def test_import_dialog_destination_button_prefills_combos(tmp_path: Path, qapp) -> None:
    """Le bouton « Choisir la destination… » ouvre l'arbre et pré-remplit
    les deux champs du formulaire (la décision finale reste éditable)."""
    from ui.views.import_dialog import ImportDialog

    previous = current_language()
    set_language("fr")  # libellés français (défaut = en)
    try:
        lib = _tree_library(tmp_path)
        src = tmp_path / "MonMod"
        src.mkdir()
        (src / "config.json").write_text("{}", encoding="utf-8")

        import app.mod_import as mod_import

        analysis = mod_import.analyze_source(src)
        dialog = ImportDialog(analysis, lib)
        assert dialog._pick_dest_btn.text() == "Choisir la destination…"

        # Monkeypatch the tree dialog's exec: user walks Primary → Bow.
        from ui.views.destination_picker import DestinationPickerDialog

        def fake_exec(self):
            primary_item = next(
                self._category_list.item(i)
                for i in range(self._category_list.count())
                if self._category_list.item(i).data(0x0100)[0] == "primary"
            )
            self._on_category_clicked(primary_item)
            bow_idx = next(
                i
                for i in range(self._weapon_list.count())
                if self._weapon_list.item(i).data(0x0100) == "Bow"
            )
            self._weapon_list.setCurrentRow(bow_idx)
            self._weapon = "Bow"
            return QDialog.Accepted

        monkeypatch_dialog = dialog
        orig_exec = DestinationPickerDialog.exec
        DestinationPickerDialog.exec = fake_exec  # type: ignore[method-assign]
        try:
            monkeypatch_dialog._pick_destination()
        finally:
            DestinationPickerDialog.exec = orig_exec  # type: ignore[method-assign]

        assert dialog._category.currentData() == "primary"
        assert dialog._weapon.currentText() == "Bow"
        plan = dialog.build_plan()
        assert plan.destination == lib / "rivals skins" / "primary" / "Bow" / "MonMod"
        dialog.deleteLater()
    finally:
        set_language(previous)


# ---------------------------------------------------------------------- #
# v1.3.1 UI regressions — search page real features, smart status, profiles
# ---------------------------------------------------------------------- #
def _make_library(root: Path) -> None:
    _write(root / "Charms" / "nemesis charm.json", {"replacement_rules": []})
    _write(
        root / "Charms" / "broken charm.json",
        {"replacement_rules": [{"mode": "local", "enabled": True,
                                "local_path": "missing model.obj"}]},
    )
    gun = root / "rivals skins" / "Primary" / "Hand gun"
    gun.mkdir(parents=True, exist_ok=True)
    _write(
        gun / "Pixelhandgun.json",
        {"replacement_rules": [{"mode": "local", "enabled": True,
                                "local_path": "Pixelboddy.obj"}]},
    )
    (gun / "Pixelboddy.obj").write_text("mesh", encoding="utf-8")


@pytest.fixture()
def ui_window(qapp, tmp_path, monkeypatch):
    from ui.main_window import MainWindow

    library = tmp_path / "lib"
    _make_library(library)
    fleasion = tmp_path / "fleasion"
    fleasion.mkdir(parents=True, exist_ok=True)
    appdata = tmp_path / "AppData"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))

    from app.config import AppSettings

    settings = AppSettings()
    settings.fleasion_dir = fleasion
    settings.library_dir = library
    settings.language = "fr"  # UI française explicitement (défaut = en)
    settings.save()

    window = MainWindow()
    window.show()
    qapp.processEvents()
    yield window, library


def test_search_page_cards_have_toggle_status_and_favorite(ui_window, qapp) -> None:
    """La page Recherche dédiée montre de vraies cartes avec le bouton
    d'activation ▶/×, l'étoile favori et la puce de statut intelligent
    (v1.3.1 : le bouton d'activation manquait sur les résultats)."""
    window, library = ui_window
    assert window._stack.currentWidget() is not window._search_view
    window._search_page_btn.click()
    qapp.processEvents()
    assert window._stack.currentWidget() is window._search_view

    sv = window._search_view
    # Le scanner condense Primary/Hand gun/ en une config « Hand gun »
    # (Pixelhandgun.json + Pixelboddy.obj = dossier-config).
    sv.set_query("Hand gun")
    window._run_search()
    qapp.processEvents()
    cards = sv._grid._cards
    assert len(cards) >= 1
    card = cards[0]
    assert card._title_label.text() == "Hand gun"
    assert card._toggle_btn.isVisible(), "le bouton ▶ / × doit exister sur les résultats"
    assert card.favorite_button is not None
    assert card._status_label.isVisible(), "la puce de statut doit exister"
    assert card._status_label.text()  # non vide : « Prête » (dépendance présente)

    # Une recherche sur la config cassée montre « Incomplète » (données
    # réelles, jamais de faux « prête »).
    sv.set_query("broken charm")
    window._run_search()
    qapp.processEvents()
    cards = sv._grid._cards
    assert len(cards) >= 1
    card = next(c for c in cards if c._title_label.text() == "broken charm")
    assert card._status_label.isVisible()
    assert "Incomplète" in card._status_label.text()


def test_search_page_clear_returns_to_recents(ui_window, qapp) -> None:
    window, library = ui_window
    window._search_page_btn.click()
    qapp.processEvents()
    sv = window._search_view
    sv.set_query("nemesis")
    window._run_search()
    qapp.processEvents()
    assert sv._grid._cards
    sv._clear_btn.click()
    qapp.processEvents()
    assert sv.query_text() == ""
    assert not sv._grid._cards  # retour à l'état « Récents »


def test_profile_capture_current_creates_card_and_persists(ui_window, qapp, monkeypatch) -> None:
    """« Enregistrer comme profil » capture la configuration actuelle en
    un clic, la carte apparaît, et le profil survit au redémarrage."""
    from PySide6.QtWidgets import QDialog

    from ui.views import profile_dialog as pd

    window, library = ui_window

    # Marquer « nemesis charm » comme active dans Fleasion (structure
    # réelle : settings.json + dossier configs/).
    import json as _json

    fleasion_root = window.settings.fleasion_dir
    (fleasion_root / "configs").mkdir(parents=True, exist_ok=True)
    (fleasion_root / "configs" / "nemesis charm.json").write_text(
        "{}", encoding="utf-8"
    )
    (fleasion_root / "settings.json").write_text(
        _json.dumps({"enabled_configs": ["nemesis charm"]}), encoding="utf-8"
    )

    calls = []

    def fake_exec(self):
        calls.append(1)
        self._name.setText("Tryhard")
        self._save_btn.click()
        return QDialog.Accepted if self.result() == QDialog.Accepted else QDialog.Rejected

    orig = pd.QDialog.exec
    pd.QDialog.exec = fake_exec
    try:
        window._save_current_as_profile()
    finally:
        pd.QDialog.exec = orig
    qapp.processEvents()

    assert calls, "le dialogue de capture doit s'ouvrir"
    profiles = window.profiles.list_profiles()
    assert len(profiles) == 1
    assert profiles[0].name == "Tryhard"
    assert [e.name for e in profiles[0].entries] == ["nemesis charm"]

    # La carte apparaît sur la page Profils.
    window._show_profiles_page()
    qapp.processEvents()
    assert [c._profile.name for c in window._profiles_view._cards] == ["Tryhard"]

    # Persistance : un nouveau fenêtre relit le même APPDATA.
    from ui.main_window import MainWindow

    window2 = MainWindow()
    window2.show()
    qapp.processEvents()
    assert window2.profiles.list_profiles()[0].name == "Tryhard"
