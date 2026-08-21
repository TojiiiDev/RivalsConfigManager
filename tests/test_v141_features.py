"""v1.3.12 — Phase 5 : le choix de destination d'import est un VRAI
sélecteur de conteneur, jamais une navigation obligeant à choisir un
élément déjà présent.

Sélecteur de destination (import individuel — « Choisir la destination ») :

* la catégorie seule est une destination (« directement dans <catégorie> ») ;
* une arme EST une destination, même vide, même pleine de skins — on n'est
  JAMAIS obligé de sélectionner un skin existant pour continuer ;
* Entrée valide immédiatement (aucune étape superflue) ;
* une destination incomplète est refusée proprement (pas d'avance) ;
* le mode profil (pick_config=True) conserve la sélection d'une
  configuration existante — profils inchangés.

Sélecteur en cascade (import en masse) :

* Catégorie → Destination : la deuxième case liste les sous-dossiers RÉELS
  de la catégorie (même vides) ;
* une catégorie sans sous-niveau (Utility, Charms...) est directement une
  destination finale ;
* chaque ligne est indépendante ; changer de catégorie met à jour SEULE
  cette ligne ;
* un nouveau nom d'arme peut toujours être tapé (création explicite) ;
* aucun nom d'élément existant n'est proposé comme destination.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QDialog

from app.i18n import t


@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _tree_library(tmp_path: Path) -> Path:
    """Primary/Assault Rifle (avec des skins) + Primary/Shotgun (vide),
    Secondary/Pistol (vide), Melee/Katana (vide), Charms (sans sous-niveau),
    Utility (absente)."""
    lib = tmp_path / "lib"
    _write_json(lib / "rivals skins" / "Primary" / "Assault Rifle" / "Skin 1.json",
                {"replacement_rules": []})
    _write_json(lib / "rivals skins" / "Primary" / "Assault Rifle" / "Skin 2.json",
                {"replacement_rules": []})
    (lib / "rivals skins" / "Primary" / "Shotgun").mkdir(parents=True)
    (lib / "rivals skins" / "Secondary" / "Pistol").mkdir(parents=True)
    (lib / "rivals skins" / "Melee" / "Katana").mkdir(parents=True)
    (lib / "Charms").mkdir(parents=True)
    return lib


def _select_category(dialog, key: str):
    """Select a category by its data key (like a real click: current item
    + handler)."""
    for i in range(dialog._category_list.count()):
        item = dialog._category_list.item(i)
        if item.data(Qt.UserRole)[0] == key:
            dialog._category_list.setCurrentItem(item)
            dialog._on_category_clicked(item)
            return item
    raise AssertionError(f"catégorie {key} introuvable")


def _select_weapon(dialog, name: str):
    for i in range(dialog._weapon_list.count()):
        item = dialog._weapon_list.item(i)
        if item.data(Qt.UserRole) == name:
            dialog._weapon_list.setCurrentRow(i)
            dialog._on_weapon_clicked(item)
            return item
    raise AssertionError(f"arme {name} introuvable")


def _enter():
    return QKeyEvent(QEvent.KeyPress, Qt.Key_Return, Qt.NoModifier)


# ---------------------------------------------------------------------- #
# 1. Import individuel — le conteneur EST la destination
# ---------------------------------------------------------------------- #
def _go_to_weapon_page(dialog, category_key: str):
    """Parcours réel : clic catégorie → Suivant (page arme)."""
    _select_category(dialog, category_key)
    dialog._go_next()
    assert dialog._stack.currentIndex() == 1


def test_picker_category_alone_is_destination(tmp_path: Path, qapp) -> None:
    """« Directement dans <catégorie> » : la catégorie seule est une
    destination valide, confirmable immédiatement."""
    from ui.views.destination_picker import DestinationPickerDialog

    lib = _tree_library(tmp_path)
    dialog = DestinationPickerDialog(lib)
    _go_to_weapon_page(dialog, "primary")
    # La catégorie seule : l'entrée « directement dans Primaire » (data None).
    for i in range(dialog._weapon_list.count()):
        item = dialog._weapon_list.item(i)
        if item.data(Qt.UserRole) is None:
            dialog._weapon_list.setCurrentRow(i)
            dialog._on_weapon_clicked(item)
            break
    dialog._go_next()
    assert dialog._stack.currentIndex() == 3  # confirmation immédiate
    assert dialog.weapon is None
    assert dialog.destination == lib / "rivals skins" / "Primary"
    dialog.deleteLater()


def test_picker_weapon_with_skins_is_destination_without_picking_skin(
    tmp_path: Path, qapp
) -> None:
    """Assault Rifle contient des skins : en mode import, l'arme EST la
    destination — on confirme sans JAMAIS sélectionner un skin existant."""
    from ui.views.destination_picker import DestinationPickerDialog

    lib = _tree_library(tmp_path)
    dialog = DestinationPickerDialog(lib)
    _go_to_weapon_page(dialog, "primary")
    _select_weapon(dialog, "Assault Rifle")
    dialog._go_next()
    # Pas de page « skins » : confirmation directe au niveau de l'arme.
    assert dialog._stack.currentIndex() == 3
    assert dialog.weapon == "Assault Rifle"
    assert dialog.selected_config is None
    assert dialog.destination == lib / "rivals skins" / "Primary" / "Assault Rifle"
    dialog.deleteLater()


def test_picker_empty_weapon_is_destination(tmp_path: Path, qapp) -> None:
    """Une arme VIDE (dossier existant sans aucun élément) est une
    destination valide — jamais « une destination n'existe que si elle
    contient déjà un élément »."""
    from ui.views.destination_picker import DestinationPickerDialog

    lib = _tree_library(tmp_path)
    dialog = DestinationPickerDialog(lib)
    _go_to_weapon_page(dialog, "primary")
    _select_weapon(dialog, "Shotgun")  # dossier vide
    dialog._go_next()
    assert dialog._stack.currentIndex() == 3
    assert dialog.destination == lib / "rivals skins" / "Primary" / "Shotgun"
    dialog.deleteLater()


def test_picker_enter_validates_immediately(tmp_path: Path, qapp) -> None:
    """Entrée valide la destination sans étape supplémentaire : avance d'une
    page, puis confirme sur la page finale."""
    from ui.views.destination_picker import DestinationPickerDialog

    lib = _tree_library(tmp_path)
    dialog = DestinationPickerDialog(lib)
    _go_to_weapon_page(dialog, "primary")
    _select_weapon(dialog, "Shotgun")
    dialog.keyPressEvent(_enter())
    assert dialog._stack.currentIndex() == 3  # arme → confirmation
    dialog.keyPressEvent(_enter())
    assert dialog.result() == QDialog.Accepted  # Entrée confirme
    dialog.deleteLater()


def test_picker_enter_advances_from_category_page(tmp_path: Path, qapp) -> None:
    """Entrée depuis la page catégorie (sélection faite) va à l'arme."""
    from ui.views.destination_picker import DestinationPickerDialog

    lib = _tree_library(tmp_path)
    dialog = DestinationPickerDialog(lib)
    _select_category(dialog, "Charms")  # catégorie réelle (dossier de premier niveau)
    dialog.keyPressEvent(_enter())
    assert dialog._stack.currentIndex() == 1
    dialog.deleteLater()


def test_picker_incomplete_destination_refused(tmp_path: Path, qapp) -> None:
    """Sans catégorie ni arme choisie, on n'avance jamais (destination
    incomplète refusée proprement)."""
    from ui.views.destination_picker import DestinationPickerDialog

    lib = _tree_library(tmp_path)
    dialog = DestinationPickerDialog(lib)
    # Aucune catégorie sélectionnée → Suivant ne fait rien.
    dialog._go_next()
    assert dialog._stack.currentIndex() == 0
    # Catégorie choisie mais aucune arme → bloqué sur la page arme.
    _select_category(dialog, "primary")
    dialog._go_next()
    assert dialog._stack.currentIndex() == 1
    dialog._weapon_list.setCurrentRow(-1)
    dialog._weapon = None
    dialog._direct_in = False
    dialog._go_next()
    assert dialog._stack.currentIndex() == 1  # toujours bloqué
    dialog.deleteLater()


def test_picker_profile_mode_still_selects_config(tmp_path: Path, qapp) -> None:
    """Le mode profil (pick_config=True) conserve la sélection d'un élément
    existant — le système de profils reste strictement inchangé."""
    from ui.views.destination_picker import DestinationPickerDialog

    lib = _tree_library(tmp_path)
    dialog = DestinationPickerDialog(lib, pick_config=True)
    _go_to_weapon_page(dialog, "primary")
    _select_weapon(dialog, "Assault Rifle")
    dialog._go_next()
    assert dialog._stack.currentIndex() == 2  # page « skins » en mode profil
    for i in range(dialog._configs_list.count()):
        if dialog._configs_list.item(i).text() == "Skin 2":
            dialog._configs_list.setCurrentRow(i)
            dialog._on_config_clicked(dialog._configs_list.item(i))
            break
    dialog._go_next()
    assert dialog._stack.currentIndex() == 3
    assert dialog.selected_config is not None
    assert dialog.selected_config.name == "Skin 2"
    dialog.deleteLater()


# ---------------------------------------------------------------------- #
# 2. Import en masse — sélecteur en cascade Catégorie → Destination
# ---------------------------------------------------------------------- #
def _batch_dialog(tmp_path: Path, qapp):
    from app.batch_import import analyze_batch, cleanup_batch
    from ui.views.batch_import_dialog import BatchImportDialog

    lib = _tree_library(tmp_path)
    _write_json(tmp_path / "AK Config" / "config.json", {"replacement_rules": []})
    _write_json(tmp_path / "Shotgun Config" / "config.json", {"replacement_rules": []})
    _write_json(tmp_path / "Pad Config" / "config.json", {"replacement_rules": []})
    _write_json(tmp_path / "Charm Config" / "config.json", {"replacement_rules": []})
    items, errors = analyze_batch(
        [tmp_path / "AK Config", tmp_path / "Shotgun Config",
         tmp_path / "Pad Config", tmp_path / "Charm Config"],
        library_root=lib,
    )
    assert errors == []
    dialog = BatchImportDialog(items, lib)
    dialog.show()
    qapp.processEvents()
    return dialog, lib, items


def test_batch_cascade_destination_lists_real_subfolders(tmp_path: Path, qapp) -> None:
    """Choisir « Primary » → la case Destination liste UNIQUEMENT les
    sous-dossiers RÉELS de Primary (Assault Rifle avec skins, Shotgun
    vide) — aucune destination générique n'apparaît."""
    dialog, _lib, _items = _batch_dialog(tmp_path, qapp)
    row = dialog._rows[0]
    row._category.setCurrentIndex(row._category.findData("primary"))
    qapp.processEvents()
    texts = [row._weapon.itemText(i) for i in range(row._weapon.count())]
    assert texts == ["Assault Rifle", "Shotgun"]  # EXACTEMENT les armes de Primary
    assert not any("directement" in t.casefold() or "directly" in t.casefold()
                   for t in texts)
    dialog.close()


def test_batch_cascade_secondary_lists_its_own_weapons(tmp_path: Path, qapp) -> None:
    """« Secondary » → la case Destination contient les armes de Secondary,
    jamais celles d'une autre catégorie."""
    dialog, _lib, _items = _batch_dialog(tmp_path, qapp)
    row = dialog._rows[0]
    row._category.setCurrentIndex(row._category.findData("secondary"))
    qapp.processEvents()
    texts = [row._weapon.itemText(i) for i in range(row._weapon.count())]
    assert "Pistol" in texts
    assert "Assault Rifle" not in texts
    assert "Katana" not in texts
    dialog.close()


def test_batch_cascade_category_change_replaces_destinations(tmp_path: Path, qapp) -> None:
    """Changer Primary → Secondary remplace immédiatement la liste des
    destinations (jamais les armes de l'ancienne catégorie)."""
    dialog, _lib, _items = _batch_dialog(tmp_path, qapp)
    row = dialog._rows[0]
    row._category.setCurrentIndex(row._category.findData("primary"))
    qapp.processEvents()
    assert "Assault Rifle" in [row._weapon.itemText(i) for i in range(row._weapon.count())]
    row._category.setCurrentIndex(row._category.findData("secondary"))
    qapp.processEvents()
    texts = [row._weapon.itemText(i) for i in range(row._weapon.count())]
    assert "Pistol" in texts
    assert "Assault Rifle" not in texts and "Shotgun" not in texts
    dialog.close()


def test_batch_cascade_weapon_with_skins_selectable(tmp_path: Path, qapp) -> None:
    """Assault Rifle (plein de skins) est sélectionnable : la destination
    est le DOSSIER, jamais un skin existant (aucun nom de skin proposé).
    La ligne n'est terminée qu'avec l'arme choisie."""
    dialog, lib, _items = _batch_dialog(tmp_path, qapp)
    row = dialog._rows[0]
    row._category.setCurrentIndex(row._category.findData("primary"))
    qapp.processEvents()
    # Primary seule (avec armes) : la ligne n'est PAS terminée.
    assert not row._row_complete()
    assert not dialog._import_btn.isEnabled()
    idx = row._weapon.findText("Assault Rifle")
    assert idx >= 0
    row._weapon.setCurrentIndex(idx)
    qapp.processEvents()
    assert row._row_complete()
    result = dialog.result_items()
    assert result[0].category == "primary"
    assert result[0].weapon == "Assault Rifle"
    # Aucun skin existant n'apparaît comme destination.
    assert all("Skin" not in row._weapon.itemText(i)
               for i in range(row._weapon.count()))
    dialog.close()


def test_batch_cascade_category_without_subs_is_final(tmp_path: Path, qapp) -> None:
    """Charms (sans sous-dossier) : la catégorie est directement la
    destination finale — la case Destination est désactivée (plus rien à
    choisir) et la validation est possible."""
    dialog, lib, _items = _batch_dialog(tmp_path, qapp)
    row = dialog._rows[0]
    row._category.setCurrentIndex(row._category.findData("Charms"))
    qapp.processEvents()
    assert not row._weapon.isEnabled()
    assert row._row_complete()  # la catégorie seule suffit
    assert row._weapon.currentData() is None  # destination = Charms
    result = dialog.result_items()
    assert result[0].category == "Charms" and result[0].weapon is None
    dialog.close()


def test_batch_cascade_rows_independent(tmp_path: Path, qapp) -> None:
    """Changer la catégorie d'une ligne ne modifie JAMAIS la destination
    d'une autre ligne."""
    dialog, lib, _items = _batch_dialog(tmp_path, qapp)
    row_a, row_b = dialog._rows[0], dialog._rows[1]
    row_a._category.setCurrentIndex(row_a._category.findData("primary"))
    qapp.processEvents()
    row_b._category.setCurrentIndex(row_b._category.findData("melee"))
    qapp.processEvents()
    # La ligne A a toujours les sous-destinations de Primary.
    assert "Assault Rifle" in [row_a._weapon.itemText(i)
                               for i in range(row_a._weapon.count())]
    # La ligne B a celles de Melee (Katana, vide).
    texts_b = [row_b._weapon.itemText(i) for i in range(row_b._weapon.count())]
    assert "Katana" in texts_b
    assert "Assault Rifle" not in texts_b
    # Les choix restent indépendants.
    row_a._weapon.setCurrentText("Shotgun")
    assert row_b._weapon.currentData() is None or row_b._weapon.currentData() != "Shotgun"
    dialog.close()


def test_batch_cascade_multiple_weapons_different_destinations(tmp_path: Path, qapp) -> None:
    """Plusieurs armes différentes sur plusieurs lignes : chaque élément
    garde sa propre destination, une seule validation."""
    dialog, lib, _items = _batch_dialog(tmp_path, qapp)
    rows = {r._item.name: r for r in dialog._rows}

    rows["AK Config"]._category.setCurrentIndex(rows["AK Config"]._category.findData("primary"))
    rows["AK Config"]._weapon.setCurrentText("Assault Rifle")

    rows["Shotgun Config"]._category.setCurrentIndex(
        rows["Shotgun Config"]._category.findData("primary"))
    rows["Shotgun Config"]._weapon.setCurrentText("Shotgun")

    rows["Pad Config"]._category.setCurrentIndex(rows["Pad Config"]._category.findData("utility"))

    rows["Charm Config"]._category.setCurrentIndex(
        rows["Charm Config"]._category.findData("Charms"))

    qapp.processEvents()
    assert dialog._import_btn.isEnabled()
    result = {i.name: i for i in dialog.result_items()}
    assert (result["AK Config"].category, result["AK Config"].weapon) == ("primary", "Assault Rifle")
    assert (result["Shotgun Config"].category, result["Shotgun Config"].weapon) == ("primary", "Shotgun")
    assert (result["Pad Config"].category, result["Pad Config"].weapon) == ("utility", None)
    assert (result["Charm Config"].category, result["Charm Config"].weapon) == ("Charms", None)
    dialog.close()


def test_batch_cascade_second_list_is_pure_selector(tmp_path: Path, qapp) -> None:
    """La deuxième liste est une VRAIE liste (non éditable) : aucun champ
    texte à remplir, aucun nom prérempli — on choisit dans la liste, et
    l'import utilise exactement ce choix."""
    dialog, lib, _items = _batch_dialog(tmp_path, qapp)
    row = dialog._rows[0]
    assert not row._weapon.isEditable()
    row._category.setCurrentIndex(row._category.findData("primary"))
    qapp.processEvents()
    assert not row._weapon.isEditable()
    assert row._weapon.isEnabled()
    texts = [row._weapon.itemText(i) for i in range(row._weapon.count())]
    assert texts == ["Assault Rifle", "Shotgun"]  # UNIQUEMENT les armes de Primary
    row._weapon.setCurrentIndex(row._weapon.findText("Shotgun"))
    qapp.processEvents()
    result = dialog.result_items()
    assert (result[0].category, result[0].weapon) == ("primary", "Shotgun")
    dialog.close()


def test_batch_cascade_no_sublevel_shows_clear_message(tmp_path: Path, qapp) -> None:
    """Une catégorie sans sous-niveau (Charms) affiche un message
    EXPLICITE (« Aucun sous-niveau — la catégorie est la destination ») —
    jamais un champ vide, jamais une saisie demandée. La catégorie EST la
    destination."""
    dialog, lib, _items = _batch_dialog(tmp_path, qapp)
    row = dialog._rows[0]
    row._category.setCurrentIndex(row._category.findData("Charms"))
    qapp.processEvents()
    assert not row._weapon.isEnabled()
    assert row._weapon.placeholderText() == t("batch_import.no_sublevel")
    assert not row._new_btn.isVisible()
    assert row._row_complete()
    result = dialog.result_items()
    assert (result[0].category, result[0].weapon) == ("Charms", None)
    dialog.close()


def test_batch_cascade_new_destination_explicit(tmp_path: Path, qapp) -> None:
    """La création d'une nouvelle destination est une action EXPLICITE et
    séparée (« + Nouvelle destination ») : le bouton est visible, le nom
    est ajouté à la liste puis sélectionné — jamais un champ texte
    automatique sur chaque ligne, jamais une destination inventée par
    détection."""
    dialog, lib, _items = _batch_dialog(tmp_path, qapp)
    row = dialog._rows[0]
    row._category.setCurrentIndex(row._category.findData("primary"))
    qapp.processEvents()
    assert row._new_btn.isVisible()
    assert row._new_btn.text() == t("batch_import.new_destination")
    row._create_destination("Railgun")
    qapp.processEvents()
    assert row._weapon.currentData() == "Railgun"
    assert "Railgun" in [row._weapon.itemText(i) for i in range(row._weapon.count())]
    assert row._row_complete()
    result = dialog.result_items()
    assert (result[0].category, result[0].weapon) == ("primary", "Railgun")
    dialog.close()


def test_batch_cascade_detection_prefills_both_levels(tmp_path: Path, qapp) -> None:
    """Une détection fiable (catégorie + arme réellement présentes dans la
    bibliothèque) prépositionne les DEUX listes ; la ligne est complète
    d'emblée, sans aucune saisie."""
    dialog, lib, _items = _batch_dialog(tmp_path, qapp)
    rows = {r._item.name: r for r in dialog._rows}
    row = rows["Shotgun Config"]
    assert row._category.currentData() == "primary"
    assert row._weapon.currentData() == "Shotgun"  # pré-sélectionnée DANS la liste
    assert row._row_complete()
    result = {i.name: i for i in dialog.result_items()}
    assert (result["Shotgun Config"].category,
            result["Shotgun Config"].weapon) == ("primary", "Shotgun")
    dialog.close()


def test_batch_cascade_import_button_updates_after_weapon_choice(
    tmp_path: Path, qapp
) -> None:
    """Choisir une arme dans la liste termine la ligne ET active
    immédiatement le bouton d'import (tout se fait en deux choix, aucune
    étape superflue, aucun signal manquant)."""
    from app.batch_import import analyze_batch
    from ui.views.batch_import_dialog import BatchImportDialog

    lib = _tree_library(tmp_path)
    _write_json(tmp_path / "ZZZ Unknown" / "config.json", {"replacement_rules": []})
    items, errors = analyze_batch([tmp_path / "ZZZ Unknown"], library_root=lib)
    assert errors == []
    dialog = BatchImportDialog(items, lib)
    dialog.show()
    qapp.processEvents()
    row = dialog._rows[0]
    assert row._category.currentData() is None  # détection absente
    assert not dialog._import_btn.isEnabled()
    row._category.setCurrentIndex(row._category.findData("primary"))
    qapp.processEvents()
    assert not dialog._import_btn.isEnabled()  # Primary seule ne suffit pas
    row._weapon.setCurrentIndex(row._weapon.findText("Assault Rifle"))
    qapp.processEvents()
    assert dialog._import_btn.isEnabled()
    dialog.close()


def test_batch_cascade_utility_lists_its_elements(tmp_path: Path, qapp) -> None:
    """« Utility » avec sous-dossiers réels (Grenade…) : la deuxième liste
    contient UNIQUEMENT les éléments de Utility ; la catégorie seule ne
    suffit plus — il faut choisir l'élément dans la liste."""
    from app.batch_import import analyze_batch
    from ui.views.batch_import_dialog import BatchImportDialog

    lib = tmp_path / "lib2"
    (lib / "Utility" / "Grenade").mkdir(parents=True)
    (lib / "Utility" / "Medkit").mkdir(parents=True)
    _write_json(tmp_path / "Spider Web" / "config.json", {"replacement_rules": []})
    items, errors = analyze_batch([tmp_path / "Spider Web"], library_root=lib)
    assert errors == []
    dialog = BatchImportDialog(items, lib)
    row = dialog._rows[0]
    row._category.setCurrentIndex(row._category.findData("utility"))
    qapp.processEvents()
    texts = [row._weapon.itemText(i) for i in range(row._weapon.count())]
    assert texts == ["Grenade", "Medkit"]  # EXACTEMENT les éléments de Utility
    assert row._weapon.isEnabled()
    assert not row._row_complete()  # la catégorie seule ne suffit plus
    row._weapon.setCurrentIndex(row._weapon.findText("Grenade"))
    qapp.processEvents()
    assert row._row_complete()
    result = dialog.result_items()
    assert (result[0].category, result[0].weapon) == ("utility", "Grenade")
    dialog.close()
