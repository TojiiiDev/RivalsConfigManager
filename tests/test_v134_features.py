"""v1.3.4 tests — favourites everywhere, user validation of dependencies,
one-click profile capture from the Fleasion folder, folder previews.

Covers the real problem cases asked for:

* Favourites: texture pack, weapon, skin, melee, charm, emote, FastFlag —
  add/remove, restart, the virtual Favourites page (file stays in its
  original category).
* Validation: a Kirambit-like configuration (MP3 flagged, actually fine),
  two texture packs, a configuration with a real missing dependency (never
  masked by default), validate / restart / reset — all generic, nothing
  hard-coded.
* Profiles: several configs present in the Fleasion folder, « Créer un
  profil » captures them all automatically (no manual selection), restart,
  apply.
* Previews: ``preview.jpg`` in the config folder is the official image;
  a fresh machine fetches the shared asset and works offline.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog, QMenu


# ---------------------------------------------------------------------- #
# Fixtures
# ---------------------------------------------------------------------- #
@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _configure(appdata: Path, library: Path, fleasion: Path) -> None:
    settings_path = appdata / "RivalsConfigManager" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps({"library_dir": str(library), "fleasion_dir": str(fleasion),
                    "language": "fr"}),
        encoding="utf-8",
    )
    fleasion.mkdir(parents=True, exist_ok=True)
    (fleasion / "settings.json").write_text("{}", encoding="utf-8")


def _full_library(root: Path) -> Path:
    """A library covering every category type mentioned in the spec."""
    lib = root / "lib"

    # Melee weapon -> skin (arme + melee + skin). Kirambit is the real
    # reported case: an MP3 is flagged as missing although the config works
    # without it (the sound is integrated). Blade is a clean config.
    katana = lib / "rivals skins" / "Melee" / "Katana"
    _write_json(
        katana / "Kirambit.json",
        {"replacement_rules": [{"enabled": True, "local_path": "Kirambit hit sound.mp3"}]},
    )
    _write_json(katana / "Blade.json", {"replacement_rules": []})

    # Primary weapon -> skin.
    ar = lib / "rivals skins" / "Primary" / "Assault Rifle"
    _write_json(ar / "ak-47.json", {"replacement_rules": []})

    # Secondary weapon with a REAL missing OBJ dependency (never masked).
    gun = lib / "rivals skins" / "Secondary" / "Hand gun"
    _write_json(
        gun / "Pixelhandgun.json",
        {"replacement_rules": [{"enabled": True, "local_path": "missing model.obj"}]},
    )

    # Charm, emote and FastFlag (flat categories).
    _write_json(lib / "Charms" / "nemesis charm.json", {"replacement_rules": []})
    _write_json(lib / "emotes" / "flossswap (1).json", {"replacement_rules": []})
    _write_json(lib / "FastFlags" / "Fleasion FastFlags.json", {"DFFlagTest": "True"})

    # Two texture packs (the other reported false-positive case): each
    # references a sound that is actually integrated — flagged missing.
    pack = lib / "Texture and skyboxes" / "Texture packs"
    _write_json(
        pack / "Minecraft_Classic.json",
        {"replacement_rules": [{"enabled": True, "local_path": "Minecraft music.mp3"}]},
    )
    _write_json(
        pack / "Faithful.json",
        {"replacement_rules": [{"enabled": True, "local_path": "Faithful ambience.mp3"}]},
    )
    import base64

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )
    (pack / "preview.jpg").write_bytes(png)

    return lib


def _fleasion_with_configs(fleasion: Path, names: list[str]) -> Path:
    """A realistic Fleasion structure: settings.json + configs/<name>.json."""
    root = fleasion
    (root / "configs").mkdir(parents=True, exist_ok=True)
    for name in names:
        (root / "configs" / f"{name}.json").write_text("{}", encoding="utf-8")
    (root / "settings.json").write_text(
        json.dumps({"enabled_configs": names, "last_config": names[-1] if names else None}),
        encoding="utf-8",
    )
    return root


@pytest.fixture()
def ui_window(qapp, tmp_path, monkeypatch):
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    lib = _full_library(tmp_path)
    fleasion = tmp_path / "fleasion"
    fleasion.mkdir(parents=True)
    _configure(appdata, lib, fleasion)
    window = MainWindow()
    window.show()
    qapp.processEvents()
    yield window
    window.deleteLater()


# ---------------------------------------------------------------------- #
# 1. Favourites — the same mechanism on every category
# ---------------------------------------------------------------------- #
def test_favorite_star_on_every_category(ui_window, qapp) -> None:
    """L'étoile favori existe sur TOUTES les cartes de configuration : arme,
    skin, melee, charm, emote, FastFlag et packs de textures — le même
    mécanisme que sur les packs de textures, nulle part dupliqué."""
    from app.scanner import find_node
    from app.sync import walk_configs

    configs = walk_configs(ui_window.root_node)
    names = {c.name for c in configs}
    assert {
        "Kirambit", "Blade", "ak-47", "Pixelhandgun", "nemesis charm",
        "flossswap (1)", "Fleasion FastFlags", "Minecraft_Classic", "Faithful",
    } <= names

    # Chaque carte config (sur la page de son dossier) porte l'étoile.
    for config in configs:
        key = str(config.path)
        folder = find_node(ui_window.root_node, config.path.parent)
        assert folder is not None, f"dossier introuvable pour {config.name}"
        ui_window.go(("browse", folder))
        qapp.processEvents()
        card = ui_window._browse._grid.find_card(key)
        assert card is not None, f"carte manquante pour {config.name}"
        assert card.favorite_button is not None, f"étoile manquante sur {config.name}"
        assert card.favorite_button.isVisible(), f"étoile invisible sur {config.name}"


def _real_like_library(root: Path) -> Path:
    """Réplique de la structure RÉELLE : les catégories (primary/secondary/
    melee/utility) et les armes sont des DOSSIERS (Node), les skins et
    charms des fichiers, le pack de textures une folder-configuration."""
    lib = root / "lib"

    (lib / "Charms").mkdir(parents=True)
    (lib / "Charms" / "nemesis charm.json").write_text("{}", encoding="utf-8")
    (lib / "emotes").mkdir(parents=True)
    (lib / "emotes" / "flossswap (1).json").write_text("{}", encoding="utf-8")
    (lib / "FastFlags").mkdir(parents=True)
    (lib / "FastFlags" / "Fleasion FastFlags.json").write_text("{}", encoding="utf-8")

    # Pack de textures : 1 seul JSON dans un dossier -> folder-config.
    pack = lib / "Textures and skyboxes" / "gun texture pack"
    pack.mkdir(parents=True)
    (pack / "crimvals.json").write_text("{}", encoding="utf-8")

    # Catégories (dossiers) -> armes (dossiers) -> skins (fichiers).
    ar = lib / "rivals skins" / "primary" / "Assault Rifle"
    ar.mkdir(parents=True)
    (ar / "ak-47.json").write_text("{}", encoding="utf-8")
    bow = lib / "rivals skins" / "primary" / "Bow"
    bow.mkdir(parents=True)
    (bow / "longbow.json").write_text("{}", encoding="utf-8")
    gun = lib / "rivals skins" / "secondary" / "Hand gun"
    gun.mkdir(parents=True)
    (gun / "Pixelhandgun.json").write_text("{}", encoding="utf-8")
    katana = lib / "rivals skins" / "melee" / "Katana"
    katana.mkdir(parents=True)
    (katana / "Kirambit.json").write_text("{}", encoding="utf-8")
    hook = lib / "rivals skins" / "utility" / "Grappling Hook"
    hook.mkdir(parents=True)
    (hook / "hook.json").write_text("{}", encoding="utf-8")

    return lib


@pytest.fixture()
def ui_window_real(qapp, tmp_path, monkeypatch):
    """Fenêtre sur une bibliothèque au format réel (catégories/armes =
    dossiers, skins = fichiers, packs = folder-configs)."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    lib = _real_like_library(tmp_path)
    fleasion = tmp_path / "fleasion"
    fleasion.mkdir(parents=True)
    _configure(appdata, lib, fleasion)
    window = MainWindow()
    window.show()
    qapp.processEvents()
    yield window
    window.deleteLater()


def _browse_card(window, qapp, path: Path):
    """Naviguer jusqu'au dossier contenant ``path`` et retourner sa carte."""
    from app.scanner import find_node

    folder = find_node(window.root_node, path.parent)
    assert folder is not None, f"dossier introuvable : {path.parent}"
    window.go(("browse", folder))
    qapp.processEvents()
    card = window._browse._grid.find_card(str(path))
    assert card is not None, f"carte manquante pour {path}"
    return card


def test_favorite_star_on_every_card_type(ui_window_real, qapp) -> None:
    """L'étoile favori distingue proprement les cartes : les catégories de
    NAVIGATION (primary/secondary/melee/utility) n'en ont PAS ; les vrais
    éléments utilisables (pack Texture & Skybox = folder-config, armes,
    skins, charms, emotes, FastFlags) en ont une — exactement le même
    composant partout (même emplacement, même interaction)."""
    from app.scanner import find_node

    window = ui_window_real
    lib = window.settings.library_dir

    # ---- Texture & Skybox : le pack (folder-config) porte l'étoile. ---- #
    pack = _browse_card(window, qapp, lib / "Textures and skyboxes" / "gun texture pack" / "crimvals.json")
    assert pack.favorite_button is not None and pack.favorite_button.isVisible()

    # ---- Page « rivals skins » : les catégories (primary/secondary/melee/
    # utility) sont de la NAVIGATION pure → PAS d'étoile. --------------- #
    skins = find_node(window.root_node, lib / "rivals skins")
    window.go(("browse", skins))
    qapp.processEvents()
    for category in ("primary", "secondary", "melee", "utility"):
        card = window._browse._grid.find_card(str(lib / "rivals skins" / category))
        assert card is not None, f"carte catégorie manquante : {category}"
        assert card.favorite_button is None, f"étoile en trop sur la catégorie {category}"

    # ---- Armes (dossiers contenant des configs) : étoile présente. ---- #
    for category, weapon in (("primary", "Assault Rifle"), ("melee", "Katana"),
                             ("secondary", "Hand gun"), ("utility", "Grappling Hook")):
        category_node = find_node(window.root_node, lib / "rivals skins" / category)
        window.go(("browse", category_node))
        qapp.processEvents()
        weapon_card = window._browse._grid.find_card(
            str(lib / "rivals skins" / category / weapon)
        )
        assert weapon_card is not None, f"carte arme manquante : {weapon}"
        assert weapon_card.favorite_button is not None and weapon_card.favorite_button.isVisible(), (
            f"étoile manquante sur l'arme {weapon}"
        )

    # ---- Skins (configs dans une arme) : étoile présente. ------------- #
    skin = _browse_card(window, qapp, lib / "rivals skins" / "melee" / "Katana" / "Kirambit.json")
    assert skin.favorite_button is not None and skin.favorite_button.isVisible()

    # ---- Charm / emote / FastFlag (configs) : étoile présente. -------- #
    charm = _browse_card(window, qapp, lib / "Charms" / "nemesis charm.json")
    assert charm.favorite_button is not None and charm.favorite_button.isVisible()
    emote = _browse_card(window, qapp, lib / "emotes" / "flossswap (1).json")
    assert emote.favorite_button is not None and emote.favorite_button.isVisible()
    flag = _browse_card(window, qapp, lib / "FastFlags" / "Fleasion FastFlags.json")
    assert flag.favorite_button is not None and flag.favorite_button.isVisible()


def test_favorite_weapon_folder_toggle_favorites_view_and_restart(ui_window_real, qapp, tmp_path, monkeypatch) -> None:
    """Ajout/retrait d'un favori sur une ARME (dossier) : la carte apparaît
    dans la vue Favoris (carte dossier), un clic ouvre la page du dossier,
    la persistance survit au redémarrage, le retrait laisse le fichier en
    place dans sa catégorie d'origine."""
    from app.scanner import find_node
    from ui.main_window import PAGE_FAVORITES, MainWindow

    window = ui_window_real
    lib = window.settings.library_dir
    weapon_path = lib / "rivals skins" / "melee" / "Katana"
    weapon_node = find_node(window.root_node, weapon_path)
    assert weapon_node is not None

    # 1. Ajouter l'arme (dossier) aux favoris via l'étoile de sa carte
    #    (la carte « Katana » se trouve sur la page « melee »).
    melee_node = find_node(window.root_node, weapon_path.parent)
    window.go(("browse", melee_node))
    qapp.processEvents()
    weapon_card = window._browse._grid.find_card(str(weapon_path))
    assert weapon_card is not None and weapon_card.favorite_button is not None
    weapon_card.favorite_button.click()
    qapp.processEvents()
    assert window.settings.is_favorite(str(weapon_path))
    assert weapon_card.is_favorite()

    # 2. La vue Favoris montre la carte dossier ; clic -> page du dossier.
    window.go((PAGE_FAVORITES, None))
    qapp.processEvents()
    titles = {c._title_label.text() for c in window._favorites_view._grid._cards}
    assert "Katana" in titles
    folder_card = window._favorites_view._grid.find_card(str(weapon_path))
    assert folder_card is not None and folder_card.favorite_button is not None
    folder_card.clicked.emit()
    qapp.processEvents()
    assert window._stack.currentWidget() is window._browse
    assert window._history.current()[1].path == weapon_path

    # 3. Le dossier reste dans sa catégorie d'origine.
    assert weapon_path.exists()
    assert (weapon_path / "Kirambit.json").exists()

    # 4. Persistance après redémarrage.
    appdata = tmp_path / "AppData" / "Roaming"
    window2 = MainWindow()
    window2.show()
    qapp.processEvents()
    assert str(weapon_path) in window2.settings.favorites
    window2.go((PAGE_FAVORITES, None))
    qapp.processEvents()
    assert "Katana" in {c._title_label.text() for c in window2._favorites_view._grid._cards}

    # 5. Retrait : la carte quitte la vue Favoris, le dossier reste.
    window2._favorites_view._grid.find_card(str(weapon_path)).favorite_button.click()
    qapp.processEvents()
    assert not window2.settings.is_favorite(str(weapon_path))
    assert weapon_path.exists()
    window2.deleteLater()


def test_favorite_toggle_add_remove_and_favorites_page(ui_window, qapp) -> None:
    """Ajout/retrait sur plusieurs catégories : la carte apparaît dans la
    vue Favoris, reste dans sa catégorie d'origine, et le retrait retire la
    carte de la vue Favoris sans jamais toucher au fichier."""
    from app.sync import walk_configs
    from ui.main_window import PAGE_FAVORITES

    by_name = {c.name: c for c in walk_configs(ui_window.root_node)}
    targets = [
        by_name["Kirambit"],          # melee / skin
        by_name["ak-47"],             # primary weapon skin
        by_name["nemesis charm"],     # charm
        by_name["Minecraft_Classic"],  # pack de textures
    ]
    for config in targets:
        ui_window._toggle_favorite(config)
        qapp.processEvents()
        assert ui_window.settings.is_favorite(str(config.path))

    ui_window.go((PAGE_FAVORITES, None))
    qapp.processEvents()
    titles = {c._title_label.text() for c in ui_window._favorites_view._grid._cards}
    assert {c.name for c in targets} <= titles

    # Les fichiers restent dans leur catégorie d'origine.
    for config in targets:
        assert config.path.exists()

    # Retrait : la carte quitte la vue Favoris, le fichier reste.
    ui_window._toggle_favorite(by_name["Kirambit"])
    qapp.processEvents()
    remaining = {c._title_label.text() for c in ui_window._favorites_view._grid._cards}
    assert "Kirambit" not in remaining
    assert by_name["Kirambit"].path.exists()


def test_favorites_survive_restart(tmp_path: Path, qapp, monkeypatch) -> None:
    from app.sync import walk_configs
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    lib = _full_library(tmp_path)
    fleasion = tmp_path / "fleasion"
    fleasion.mkdir(parents=True)
    _configure(appdata, lib, fleasion)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    target = next(c for c in walk_configs(window.root_node) if c.name == "Blade")
    window.settings.toggle_favorite(str(target.path))
    window.settings.save()
    window.deleteLater()

    fresh = MainWindow()
    fresh.show()
    qapp.processEvents()
    assert str(target.path) in fresh.settings.favorites
    # L'étoile est restaurée sur la carte (dans sa catégorie d'origine).
    from app.scanner import find_node

    folder = find_node(fresh.root_node, target.path.parent)
    fresh.go(("browse", folder))
    qapp.processEvents()
    card = fresh._browse._grid.find_card(str(target.path))
    assert card is not None
    assert card.is_favorite()
    fresh.deleteLater()


# ---------------------------------------------------------------------- #
# 2. Validation — neutraliser un faux positif, génériquement
# ---------------------------------------------------------------------- #
def _patch_qmessagebox_yes(monkeypatch, yes_text: str) -> dict:
    """Remplacer exec() du QMessageBox : l'utilisateur clique « Oui »."""
    from PySide6.QtWidgets import QMessageBox

    captured = {}

    def fake_exec(box):
        captured["question"] = box.text()
        for button in box.buttons():
            if yes_text in button.text():
                box.clickedButton = lambda: button
                return QDialog.Accepted
        return QDialog.Rejected

    monkeypatch.setattr(QMessageBox, "exec", fake_exec)
    return captured


def test_validation_kirambit_like_flow(ui_window, qapp, monkeypatch) -> None:
    """Kirambit-like : MP3 signalée manquante → « Incomplète » ; l'utilisateur
    valide (« ✓ Oui, elle fonctionne ») → la dépendance n'est plus bloquante,
    « ✓ Validée » s'affiche, la carte repasse « Prête » ; la validation
    survit au redémarrage ; la réinitialisation restaure « Incomplète »."""
    from app.sync import walk_configs

    item = next(c for c in walk_configs(ui_window.root_node) if c.name == "Kirambit")

    # Avant validation : dépendance MP3 manquante → statut « Incomplète ».
    assert ui_window._smart_status_for(item) == "incomplete"
    assert not ui_window.validations.is_validated(str(item.path))

    ui_window.go(("config", item))
    qapp.processEvents()
    assert ui_window._config._validate_btn.isVisible(), "le contrôle « ✓ Valider » doit être visible"
    assert ui_window._config._validate_btn.text() == "✓ Valider"

    # Clic « ✓ Valider » → confirmation : l'utilisateur choisit « Oui ».
    answered = _patch_qmessagebox_yes(monkeypatch, "Oui")
    ui_window._config._validate_btn.click()
    qapp.processEvents()

    assert "Cette configuration fonctionne-t-elle correctement" in answered["question"]
    assert ui_window.validations.is_validated(str(item.path))
    # La dépendance n'est plus affichée comme bloquante.
    assert ui_window._config._validated_label.isVisible()
    assert "Validée" in ui_window._config._validated_label.text()
    assert ui_window._config._reset_validation_btn.isVisible()
    assert "non bloquante" in ui_window._config._deps_content.text().lower() or \
        "ignorées" in ui_window._config._deps_content.text().lower()
    # La puce de statut de la carte n'est plus « Incomplète ».
    assert ui_window._smart_status_for(item) == "ready"

    # Redémarrage : la validation est persistée.
    from ui.main_window import MainWindow

    appdata = os.environ["APPDATA"]
    window2 = MainWindow()
    window2.show()
    qapp.processEvents()
    item2 = next(c for c in walk_configs(window2.root_node) if c.name == "Kirambit")
    assert window2.validations.is_validated(str(item2.path))
    assert window2._smart_status_for(item2) == "ready"
    window2.go(("config", item2))
    qapp.processEvents()
    assert window2._config._validated_label.isVisible()

    # Réinitialisation : la dépendance redevient bloquante.
    window2._config._reset_validation_btn.click()
    qapp.processEvents()
    assert not window2.validations.is_validated(str(item2.path))
    assert window2._smart_status_for(item2) == "incomplete"
    assert window2._config._validate_btn.isVisible()
    window2.deleteLater()


def test_validation_can_be_declined(ui_window, qapp, monkeypatch) -> None:
    """« Non » au dialogue → aucune validation enregistrée."""
    from PySide6.QtWidgets import QMessageBox

    from app.sync import walk_configs

    item = next(c for c in walk_configs(ui_window.root_node) if c.name == "Pixelhandgun")
    ui_window.go(("config", item))
    qapp.processEvents()

    def fake_exec(box):
        for button in box.buttons():
            if "Non" in button.text():
                box.clickedButton = lambda: button
                return QDialog.Rejected
        return QDialog.Rejected

    orig_exec = QMessageBox.exec
    QMessageBox.exec = fake_exec  # type: ignore[method-assign]
    try:
        ui_window._config._validate_btn.click()
    finally:
        QMessageBox.exec = orig_exec  # type: ignore[method-assign]
    qapp.processEvents()

    assert not ui_window.validations.is_validated(str(item.path))
    assert ui_window._smart_status_for(item) == "incomplete"


def test_validation_never_masks_real_dependency(ui_window, qapp) -> None:
    """Une configuration avec une VRAIE dépendance manquante reste
    « Incomplète » tant que l'utilisateur n'a pas explicitement validé —
    aucune validation automatique, rien de codé en dur pour une config."""
    from app.sync import walk_configs

    real = next(c for c in walk_configs(ui_window.root_node) if c.name == "Pixelhandgun")
    assert ui_window._smart_status_for(real) == "incomplete"

    # La validation n'est PAS globale : les autres configs sont intactes.
    ok = next(c for c in walk_configs(ui_window.root_node) if c.name == "ak-47")
    assert ui_window._smart_status_for(ok) == "ready"

    # Rien de codé en dur : n'importe quelle config incomplète est validable.
    ui_window.validations.set_validated(str(real.path), name=real.name)
    assert ui_window._smart_status_for(real) == "ready"


def test_validation_store_persists(tmp_path: Path) -> None:
    from app.validations import ValidationStore

    store = ValidationStore(tmp_path / "validations.json")
    assert not store.is_validated("A")
    store.set_validated("A", name="Alpha", rel_path="rivals/Alpha")
    store.set_validated("B", name="Beta")
    assert store.is_validated("A") and store.is_validated("B")

    reloaded = ValidationStore(tmp_path / "validations.json")
    assert reloaded.is_validated("A")
    assert reloaded.entry("A").name == "Alpha"
    assert reloaded.entry("A").rel_path == "rivals/Alpha"
    assert not reloaded.is_validated("C")

    assert reloaded.clear_validated("A")
    assert not reloaded.clear_validated("A")
    assert not ValidationStore(tmp_path / "validations.json").is_validated("A")
    assert ValidationStore(tmp_path / "validations.json").is_validated("B")


# ---------------------------------------------------------------------- #
# 2b. « Modifier l'image » est absent de l'interface utilisateur normale
# ---------------------------------------------------------------------- #
class _RecordingMenu(QMenu):
    """QMenu whose ``exec`` never opens a modal loop: it records the
    actions and returns None (no selection) — used to inspect the card's
    context menu without blocking."""

    captured: dict = {}

    def exec(self, *args, **kwargs):  # noqa: A003 - Qt override
        _RecordingMenu.captured["actions"] = [a.text() for a in self.actions()]
        return None


def test_edit_image_hidden_from_normal_ui(ui_window_real, qapp, monkeypatch) -> None:
    """« Modifier l'image » n'apparaît plus dans l'interface utilisateur
    normale : le bouton de la page de configuration est masqué et le menu
    clic-droit des cartes ne propose plus l'action (le mécanisme reste
    intact pour une future version admin)."""
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QContextMenuEvent
    from PySide6.QtWidgets import QMenu

    from ui.widgets import card as card_mod

    window = ui_window_real

    # 1. Page de configuration : le bouton « Modifier l'image » est masqué.
    from app.sync import walk_configs

    item = next(c for c in walk_configs(window.root_node) if c.name == "ak-47")
    window.go(("config", item))
    qapp.processEvents()
    assert not window._config._edit_image_btn.isVisible()
    assert window._config._add_obj_btn.isVisible()  # les autres boutons restent
    assert window._config._remove_obj_btn.isVisible()

    # 2. Menu clic-droit d'une carte : « Supprimer » oui, « Modifier
    #    l'image » non.
    _RecordingMenu.captured = {}
    monkeypatch.setattr(card_mod, "QMenu", _RecordingMenu)
    card = card_mod.Card("Un test", "")
    event = QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(10, 10), QPoint(50, 50))
    card.contextMenuEvent(event)
    qapp.processEvents()
    actions = _RecordingMenu.captured.get("actions", [])
    assert "Modifier l'image" not in actions
    assert "Supprimer" in actions


def test_edit_image_admin_flag_re_enables(monkeypatch, qapp) -> None:
    """La préparation admin (v1.3.5) : une SEULE porte centrale
    (``ADMIN_MODE`` / ``admin_enabled()``) — la retourner à True réactive
    « Modifier l'image » dans le menu clic-droit, sans aucun « if admin »
    dispersé dans l'interface."""
    import app.config as config_mod
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QContextMenuEvent
    from PySide6.QtWidgets import QMenu

    from ui.widgets import card as card_mod

    assert config_mod.admin_enabled() is False
    monkeypatch.setattr(config_mod, "ADMIN_MODE", True)

    _RecordingMenu.captured = {}
    monkeypatch.setattr(card_mod, "QMenu", _RecordingMenu)
    card = card_mod.Card("Un test", "")
    event = QContextMenuEvent(QContextMenuEvent.Mouse, QPoint(10, 10), QPoint(50, 50))
    card.contextMenuEvent(event)
    qapp.processEvents()
    actions = _RecordingMenu.captured.get("actions", [])
    assert "Modifier l'image" in actions


# ---------------------------------------------------------------------- #
# 3. Profiles — one-click capture of the Fleasion state
# ---------------------------------------------------------------------- #
def test_profile_create_captures_all_fleasion_configs(ui_window, qapp, monkeypatch) -> None:
    """Plusieurs configurations présentes dans Fleasion → « Créer un profil »
    les récupère TOUTES automatiquement (récap en lecture seule + nom), le
    profil apparaît immédiatement, survit au redémarrage et s'applique."""
    from PySide6.QtWidgets import QDialog as _QDialog

    from app.sync import walk_configs
    from ui.views import profile_dialog as pd

    # 1. L'utilisateur a configuré Fleasion : plusieurs configs présentes.
    _fleasion_with_configs(
        ui_window.settings.fleasion_dir,
        ["Kirambit", "ak-47", "nemesis charm", "Minecraft_Classic"],
    )

    seen = {}

    def fake_exec(dialog):
        seen["dialog"] = dialog
        seen["count"] = len(dialog._capture)
        seen["names"] = [c.name for c in dialog._capture]
        # Lecture seule : aucune case à cocher.
        from PySide6.QtCore import Qt

        seen["checkable"] = any(
            bool(dialog._list.item(i).flags() & Qt.ItemIsUserCheckable)
            for i in range(dialog._list.count())
        )
        seen["label"] = dialog._configs_label.text()
        seen["save_text"] = dialog._save_btn.text()
        dialog._name.setText("Tryhard")
        dialog._save_btn.click()
        return _QDialog.Accepted if dialog.result() == _QDialog.Accepted else _QDialog.Rejected

    orig_exec = pd.QDialog.exec
    pd.QDialog.exec = fake_exec  # type: ignore[method-assign]
    try:
        ui_window._create_profile()
    finally:
        pd.QDialog.exec = orig_exec  # type: ignore[method-assign]
    qapp.processEvents()

    assert seen.get("dialog") is not None, "le dialogue doit s'ouvrir"
    assert seen["count"] == 4, "toutes les configs présentes dans Fleasion doivent être capturées"
    assert set(seen["names"]) == {"Kirambit", "ak-47", "nemesis charm", "Minecraft_Classic"}
    assert "27" not in str(seen["count"])  # le compte réel, jamais une valeur en dur
    label = seen["label"].lower()
    assert "détectées dans fleasion" in label or "detected in fleasion" in label
    assert seen["save_text"] == "Créer un profil"
    assert not seen["checkable"], "aucune sélection manuelle en mode capture"

    profiles = ui_window.profiles.list_profiles()
    assert len(profiles) == 1
    profile = profiles[0]
    assert profile.name == "Tryhard"
    assert {e.name for e in profile.entries} == {
        "Kirambit", "ak-47", "nemesis charm", "Minecraft_Classic"
    }
    # Références logiques : chemins relatifs à la bibliothèque, jamais absolus.
    for entry in profile.entries:
        assert not Path(entry.rel_path).is_absolute()
        assert ":" not in entry.rel_path
    assert all(
        (ui_window.settings.library_dir / e.rel_path).exists()
        for e in profile.entries
    )

    # La carte apparaît immédiatement sur la page Profils.
    ui_window._show_profiles_page()
    qapp.processEvents()
    assert [c._profile.name for c in ui_window._profiles_view._cards] == ["Tryhard"]

    # Redémarrage : le profil survit.
    from ui.main_window import MainWindow

    window2 = MainWindow()
    window2.show()
    qapp.processEvents()
    assert window2.profiles.list_profiles()[0].name == "Tryhard"
    assert window2._profile_missing(window2.profiles.get("Tryhard")) == []

    # Application : le mécanisme Fleasion existant est utilisé.
    ui_window._apply_profile(profile)
    qapp.processEvents()
    window2.deleteLater()


def test_profile_create_no_configs_never_empty(ui_window, qapp, monkeypatch) -> None:
    """Dossier Fleasion sans configuration → message clair, AUCUN profil
    vide créé silencieusement, aucun dialogue ouvert."""
    from ui.views import profile_dialog as pd

    opened = []
    orig_exec = pd.QDialog.exec

    def _fake_exec(dialog):
        opened.append(dialog)
        return QDialog.Rejected

    pd.QDialog.exec = _fake_exec  # type: ignore[method-assign]
    try:
        ui_window._create_profile()
    finally:
        pd.QDialog.exec = orig_exec  # type: ignore[method-assign]
    qapp.processEvents()

    assert opened == [], "aucun dialogue ne doit s'ouvrir sans config à capturer"
    assert ui_window.profiles.list_profiles() == []


def test_profile_create_inaccessible_fleasion(ui_window, qapp, monkeypatch) -> None:
    """Dossier Fleasion inaccessible → erreur claire, aucun profil créé."""
    from ui.views import profile_dialog as pd

    ui_window.settings.fleasion_dir = ui_window.settings.fleasion_dir / "nope"
    opened = []
    orig_exec = pd.QDialog.exec

    def _fake_exec(dialog):
        opened.append(dialog)
        return QDialog.Rejected

    pd.QDialog.exec = _fake_exec  # type: ignore[method-assign]
    try:
        ui_window._create_profile()
    finally:
        pd.QDialog.exec = orig_exec  # type: ignore[method-assign]
    qapp.processEvents()

    assert opened == []
    assert ui_window.profiles.list_profiles() == []


def test_save_current_as_profile_captures_fleasion(ui_window, qapp, monkeypatch) -> None:
    """« Enregistrer comme profil » : même capture instantanée (l'état du
    dossier Fleasion, sans sélection manuelle)."""
    from ui.views import profile_dialog as pd

    _fleasion_with_configs(
        ui_window.settings.fleasion_dir,
        ["Kirambit", "Blade", "ak-47"],
    )
    seen = {}

    def _fake_exec(dialog):
        seen["count"] = len(dialog._capture)
        dialog._name.setText("Ranked")
        dialog._save_btn.click()
        return QDialog.Accepted if dialog.result() == QDialog.Accepted else QDialog.Rejected

    orig_exec = pd.QDialog.exec
    pd.QDialog.exec = _fake_exec  # type: ignore[method-assign]
    try:
        ui_window._save_current_as_profile()
    finally:
        pd.QDialog.exec = orig_exec  # type: ignore[method-assign]
    qapp.processEvents()

    assert seen.get("count") == 3
    profiles = ui_window.profiles.list_profiles()
    assert len(profiles) == 1 and profiles[0].name == "Ranked"
    assert {e.name for e in profiles[0].entries} == {"Kirambit", "Blade", "ak-47"}


# ---------------------------------------------------------------------- #
# 4. Previews — preview.jpg is the official image
# ---------------------------------------------------------------------- #
def test_preview_jpg_in_folder_is_used(tmp_path: Path, qapp, monkeypatch) -> None:
    """``preview.jpg`` directement dans le dossier de la configuration devient
    l'image officielle de la carte (placeholder si absente)."""
    import base64

    from app.scanner import scan_library

    lib = tmp_path / "lib"
    (lib / "MaConfig").mkdir(parents=True)
    (lib / "MaConfig" / "config.json").write_text("{}", encoding="utf-8")
    (lib / "MaConfig" / "fichier.obj").write_text("mesh", encoding="utf-8")
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )
    (lib / "MaConfig" / "preview.jpg").write_bytes(png)

    result = scan_library(lib)
    assert result.ok
    config = result.node.configs[0]
    assert config.name == "MaConfig"
    assert config.preview is not None
    assert config.preview.name == "preview.jpg"
    assert config.preview in config.files

    # Sans preview : placeholder (pas de crash, pas d'image inventée).
    (lib / "MaConfig" / "preview.jpg").unlink()
    result2 = scan_library(lib)
    config2 = result2.node.configs[0]
    assert config2.preview is None


def test_preview_jpg_beats_other_images_in_folder(tmp_path: Path, qapp) -> None:
    """Priorité : ``preview`` prime sur les autres images du dossier."""
    from app.scanner import find_preview

    folder = tmp_path / "pack"
    folder.mkdir()
    (folder / "screenshot.png").write_bytes(b"png")
    (folder / "preview.jpg").write_bytes(b"jpg")
    assert find_preview(folder).name == "preview.jpg"


def test_preview_works_offline_after_fetch(tmp_path: Path, qapp, monkeypatch) -> None:
    """Machine vierge : le cache local conserve la preview téléchargée depuis
    GitHub (manifest simulé) et elle reste affichable hors ligne."""
    import base64

    from app.assets.cache import LocalAssetCache
    from app.assets.manifest import AssetManifest, AssetEntry
    from app.image_metadata import effective_preview, invalidate_shared_assets
    from app.scanner import find_config, scan_library

    appdata = tmp_path / "AppData"
    appdata.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata))
    invalidate_shared_assets()

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )
    cache = LocalAssetCache()
    entry = AssetEntry(
        key="texture_and_skyboxes/texture_packs/minecraft_classic",
        path="assets/texture_and_skyboxes/texture_packs/minecraft_classic.png",
        version=1,
    )
    cache.write_manifest(
        AssetManifest(schema_version=1, assets_version="x", assets={entry.key: entry})
    )
    dest = cache.file_for(entry.path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(png)

    lib = tmp_path / "lib"
    (lib / "Texture and skyboxes" / "Texture packs").mkdir(parents=True)
    (lib / "Texture and skyboxes" / "Texture packs" / "Minecraft_Classic.json").write_text(
        "{}", encoding="utf-8"
    )
    result = scan_library(lib)
    config = find_config(
        result.node, lib / "Texture and skyboxes" / "Texture packs" / "Minecraft_Classic.json"
    )
    assert config is not None
    preview = effective_preview(config)
    assert preview is not None and preview.is_file()
    assert preview == dest
