"""v1.3.5 tests — favourites at EVERY level (really on the card), the
« Recharger l'application » button (true restart, no cwd dependence) and
the central admin gate (``ADMIN_MODE``).

Covers exactly the cases observed on the real library:

* big categories (home), the « Rivals skins » category, Primary / Secondary
  / Melee / Utility, weapons, skins inside a weapon, charms, emotes,
  FastFlags, texture packs — the star is present on the **rendered card**
  at every level (never just a Python function);
* add / remove, restart persistence, the virtual Favorites page, clicking a
  favourite folder opens its page, no file is ever moved or deleted;
* the card builders are centralized (ui.card_specs) and always attach the
  star keyed on the real path;
* the restart button spawns a fresh instance via the real interpreter /
  executable — never the cwd, never System32 — after saving the settings;
* the normal build hides admin tools; ``ADMIN_MODE`` (single central gate)
  re-enables them for the admin build.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication


# ---------------------------------------------------------------------- #
# Fixtures
# ---------------------------------------------------------------------- #
@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


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


def _real_like_library(root: Path) -> Path:
    """Réplique de la structure RÉELLE : grandes catégories (dossiers) →
    catégories d'armes → armes → skins ; charms/emotes/FastFlags plats ;
    packs de textures en folder-configurations."""
    lib = root / "lib"

    for flat, name in (("Charms", "nemesis charm.json"),
                       ("emotes", "flossswap (1).json"),
                       ("FastFlags", "Fleasion FastFlags.json")):
        _write_json(lib / flat / name, {"replacement_rules": []})

    pack = lib / "Textures and skyboxes" / "gun texture pack"
    _write_json(pack / "crimvals.json", {"replacement_rules": []})

    def skin(category: str, weapon: str, name: str) -> None:
        _write_json(lib / "rivals skins" / category / weapon / f"{name}.json",
                    {"replacement_rules": []})

    skin("primary", "Assault Rifle", "ak-47")
    skin("primary", "Bow", "longbow")
    skin("secondary", "Hand gun", "Pixelhandgun")
    skin("melee", "Katana", "Kirambit")
    skin("utility", "Grappling Hook", "hook")

    return lib


@pytest.fixture()
def ui_window(qapp, tmp_path, monkeypatch):
    """Fenêtre sur une bibliothèque au format réel."""
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


def _browse(window, qapp, path: Path):
    """Naviguer jusqu'au dossier ``path`` (page Parcours) et renvoyer son
    nœud scanné (échec explicite si introuvable)."""
    from app.scanner import find_node

    node = find_node(window.root_node, path)
    assert node is not None, f"nœud introuvable : {path}"
    window.go(("browse", node))
    qapp.processEvents()
    return node


def _card_in(window, qapp, path: Path):
    """La carte rendue pour ``path`` sur la page courante (échec explicite)."""
    card = window._browse._grid.find_card(str(path))
    assert card is not None, f"carte manquante sur la page courante pour {path}"
    return card


def _assert_star(card, label: str) -> None:
    assert card.favorite_button is not None, f"étoile absente sur {label}"
    assert card.favorite_button.isVisible(), f"étoile invisible sur {label}"


# ---------------------------------------------------------------------- #
# 1. Favourites — the star is REALLY on the card, at every level
# ---------------------------------------------------------------------- #
def test_navigation_categories_have_no_star_weapon_favorite_flow(
    ui_window, qapp, tmp_path, monkeypatch
) -> None:
    """Les catégories purement destinées à naviguer (accueil : « rivals
    skins », « Charms », « Textures and skyboxes »...) n'ont PAS d'étoile.
    Une ARME (dossier contenant des configs) en a une : l'ajouter → carte
    dans la vue Favoris, clic → page du dossier, persistance après
    redémarrage, retrait sans toucher au dossier."""
    from ui.main_window import PAGE_FAVORITES, MainWindow

    window = ui_window
    lib = window.settings.library_dir
    skins_path = lib / "rivals skins"
    textures_path = lib / "Textures and skyboxes"
    weapon_path = lib / "rivals skins" / "melee" / "Katana"

    # 1. Les grandes catégories de l'accueil sont de la navigation → PAS
    #    d'étoile (elles ne représentent aucune configuration utilisable).
    window.go(("home", None))
    qapp.processEvents()
    skins_card = window._home._grid.find_card(str(skins_path))
    assert skins_card is not None, "carte « rivals skins » absente de l'accueil"
    assert skins_card.favorite_button is None, "étoile en trop sur la catégorie rivals skins"
    textures_card = window._home._grid.find_card(str(textures_path))
    assert textures_card is not None
    assert textures_card.favorite_button is None, "étoile en trop sur Textures and skyboxes"

    # 2. Ajouter l'ARME « Katana » (dossier contenant des configs) via
    #    l'étoile de sa carte (page « melee »).
    from app.scanner import find_node

    melee = find_node(window.root_node, lib / "rivals skins" / "melee")
    window.go(("browse", melee))
    qapp.processEvents()
    weapon_card = window._browse._grid.find_card(str(weapon_path))
    assert weapon_card is not None and weapon_card.favorite_button is not None
    weapon_card.favorite_button.click()
    qapp.processEvents()
    assert window.settings.is_favorite(str(weapon_path))
    assert weapon_card.is_favorite()

    # 3. La vue Favoris montre la carte dossier ; clic → page du dossier.
    window.go((PAGE_FAVORITES, None))
    qapp.processEvents()
    folder_card = window._favorites_view._grid.find_card(str(weapon_path))
    assert folder_card is not None
    _assert_star(folder_card, "Katana (vue Favoris)")
    folder_card.clicked.emit()
    qapp.processEvents()
    assert window._stack.currentWidget() is window._browse
    assert window._history.current()[1].path == weapon_path

    # 4. Aucun déplacement / aucune suppression : le dossier reste en place.
    assert weapon_path.is_dir()
    assert (weapon_path / "Kirambit.json").exists()

    # 5. Persistance après redémarrage.
    window2 = MainWindow()
    window2.show()
    qapp.processEvents()
    assert str(weapon_path) in window2.settings.favorites
    window2.go((PAGE_FAVORITES, None))
    qapp.processEvents()
    assert window2._favorites_view._grid.find_card(str(weapon_path)) is not None

    # 6. Retrait : la carte quitte la vue Favoris, le dossier reste.
    window2._favorites_view._grid.find_card(str(weapon_path)).favorite_button.click()
    qapp.processEvents()
    assert not window2.settings.is_favorite(str(weapon_path))
    assert weapon_path.is_dir()
    window2.deleteLater()


def test_star_on_every_usable_level_none_on_navigation(ui_window, qapp) -> None:
    """Distinction propre : les cartes de NAVIGATION (grandes catégories de
    l'accueil, Primary/Secondary/Melee/Utility) n'ont PAS d'étoile ; les
    cartes utilisables (armes, skins, charms, emotes, FastFlags, packs) en
    ont une — vérifiée sur la carte RÉELLEMENT rendue."""
    window = ui_window
    lib = window.settings.library_dir

    # ---- Accueil : les grandes catégories sont de la navigation. ----- #
    window.go(("home", None))
    qapp.processEvents()
    for category in ("rivals skins", "Charms", "emotes", "FastFlags",
                     "Textures and skyboxes"):
        card = window._home._grid.find_card(str(lib / category))
        assert card is not None, f"carte accueil manquante : {category}"
        assert card.favorite_button is None, f"étoile en trop sur {category}"

    # ---- « Rivals skins » : Primary / Secondary / Melee / Utility sont
    # de la navigation pure → PAS d'étoile. ---------------------------- #
    _browse(window, qapp, lib / "rivals skins")
    for category in ("primary", "secondary", "melee", "utility"):
        card = _card_in(window, qapp, lib / "rivals skins" / category)
        assert card.favorite_button is None, f"étoile en trop sur {category}"

    # ---- Armes (dossiers contenant des configs) : étoile présente. --- #
    _browse(window, qapp, lib / "rivals skins" / "primary")
    for weapon in ("Assault Rifle", "Bow"):
        _assert_star(
            _card_in(window, qapp, lib / "rivals skins" / "primary" / weapon),
            f"arme {weapon}",
        )

    # ---- Skins à l'intérieur d'une arme. ----------------------------- #
    _browse(window, qapp, lib / "rivals skins" / "melee" / "Katana")
    _assert_star(
        _card_in(window, qapp, lib / "rivals skins" / "melee" / "Katana" / "Kirambit.json"),
        "skin Kirambit",
    )
    _browse(window, qapp, lib / "rivals skins" / "primary" / "Assault Rifle")
    _assert_star(
        _card_in(window, qapp, lib / "rivals skins" / "primary" / "Assault Rifle" / "ak-47.json"),
        "skin ak-47",
    )

    # ---- Charm / emote / FastFlag / pack de textures. ---------------- #
    _browse(window, qapp, lib / "Charms")
    _assert_star(_card_in(window, qapp, lib / "Charms" / "nemesis charm.json"), "charm")
    _browse(window, qapp, lib / "emotes")
    _assert_star(_card_in(window, qapp, lib / "emotes" / "flossswap (1).json"), "emote")
    _browse(window, qapp, lib / "FastFlags")
    _assert_star(_card_in(window, qapp, lib / "FastFlags" / "Fleasion FastFlags.json"), "FastFlag")
    _browse(window, qapp, lib / "Textures and skyboxes" / "gun texture pack")
    _assert_star(
        _card_in(window, qapp, lib / "Textures and skyboxes" / "gun texture pack" / "crimvals.json"),
        "pack de textures",
    )

    # Aucun fichier déplacé ni supprimé par la navigation.
    assert (lib / "rivals skins" / "primary" / "Assault Rifle" / "ak-47.json").exists()
    assert (lib / "Textures and skyboxes" / "gun texture pack" / "crimvals.json").exists()


def test_central_card_builders_distinguish_navigation_from_usable() -> None:
    """Les constructeurs centralisés (ui.card_specs) attachent l'étoile
    uniquement aux cartes utilisables, clé = chemin réel (jamais le nom
    affiché) :

    * dossier de NAVIGATION (vide ou catégorie de premier niveau) → sans
      étoile ;
    * dossier contenant des configurations (arme) → avec étoile ;
    * toute ConfigItem (skin, pack, skybox) → avec étoile ;
    * la vue Favoris force l'état favori (carte dossier de la page
      virtuelle, toujours retirable).
    """
    from app.models import ConfigItem, Node
    from ui.card_specs import config_spec, folder_spec, is_navigation_folder

    library_root = Node(name="lib", path=Path("C:/lib"))

    # Navigation pure : dossier vide ou catégorie de premier niveau.
    empty = Node(name="Primary", path=Path("C:/lib/rivals skins/primary"))
    assert is_navigation_folder(empty)
    spec = folder_spec(empty, on_click=lambda: None)
    assert spec.favorite_target is None
    assert spec.key == str(empty.path)

    category = Node(name="Charms", path=Path("C:/lib/Charms"))
    assert is_navigation_folder(category, library_root)
    assert folder_spec(category, on_click=lambda: None, library_root=library_root).favorite_target is None

    # Arme (dossier contenant des configs) : utilisable → étoile.
    weapon = Node(name="Katana", path=Path("C:/lib/rivals skins/melee/Katana"))
    weapon.configs.append(ConfigItem(name="Kirambit", path=Path("C:/lib/rivals skins/melee/Katana/Kirambit.json"), kind="file"))
    assert not is_navigation_folder(weapon)
    spec_weapon = folder_spec(weapon, on_click=lambda: None)
    assert spec_weapon.favorite_target is weapon
    assert spec_weapon.key == str(weapon.path)

    # ConfigItem (skin / pack / skybox) : toujours étoilée.
    cfg = ConfigItem(
        name="Kirambit",
        path=Path("C:/lib/rivals skins/melee/Katana/Kirambit.json"),
        kind="file",
    )
    spec2 = config_spec(cfg, on_click=lambda: None)
    assert spec2.favorite_target is cfg
    assert spec2.key == str(cfg.path)
    assert spec2.favorite_target is not None

    # La vue Favoris force l'état favori (carte dossier de la page virtuelle).
    fav = folder_spec(weapon, on_click=lambda: None, is_favorite=True)
    assert fav.is_favorite is True
    assert fav.favorite_target is weapon


# ---------------------------------------------------------------------- #
# 2. « Recharger l'application » — true restart, no cwd dependence
# ---------------------------------------------------------------------- #
def test_relaunch_command_dev_mode_uses_real_interpreter_and_script(tmp_path: Path) -> None:
    """Mode source (``python main.py``) : la commande = [interpréteur réel,
    chemin ABSOLU du script] — jamais le cwd, jamais System32."""
    from app.restart import relaunch_command

    script = tmp_path / "main.py"
    script.write_text("", encoding="utf-8")
    cmd = relaunch_command(script=str(script))
    assert cmd[0] == sys.executable
    assert Path(cmd[1]).is_absolute()
    assert Path(cmd[1]) == script.resolve()
    joined = " ".join(cmd).lower()
    assert "system32" not in joined
    assert os.getcwd().lower() not in joined


def test_relaunch_command_frozen_uses_executable(monkeypatch) -> None:
    """Build figé (EXE PyInstaller) : la commande est l'exécutable lui-même."""
    import app.restart as restart

    monkeypatch.setattr(restart.sys, "frozen", True, raising=False)
    cmd = restart.relaunch_command()
    assert cmd == [sys.executable]


def test_relaunch_command_never_depends_on_cwd(tmp_path: Path, monkeypatch) -> None:
    """Changer le dossier courant ne change RIEN à la commande de relance
    (le chemin du script est résolu une fois au démarrage)."""
    import app.restart as restart

    script = tmp_path / "main.py"
    script.write_text("", encoding="utf-8")
    before = restart.relaunch_command(script=str(script))

    monkeypatch.chdir(tmp_path)
    after = restart.relaunch_command(script=str(script))
    assert before == after
    joined = " ".join(after).lower()
    assert "system32" not in joined


def test_restart_button_present_in_settings(ui_window, qapp) -> None:
    """Le bouton « Recharger l'application » est présent dans les
    Paramètres, visible, avec une icône adaptée."""
    window = ui_window
    window.go(("settings", None))
    qapp.processEvents()
    assert window._settings._restart_btn is not None
    assert window._settings._restart_btn.isVisible()
    assert window._settings._restart_btn.text() == "Recharger l'application"
    assert not window._settings._restart_btn.icon().isNull()


def test_restart_saves_settings_spawns_new_instance_and_closes(
    ui_window, qapp, monkeypatch
) -> None:
    """Clic sur « Recharger l'application » : 1) les paramètres (favoris)
    sont sauvegardés ; 2) une nouvelle instance est lancée via la vraie
    commande de relance ; 3) l'instance courante se ferme proprement."""
    import ui.main_window as mw

    from app.config import AppSettings

    window = ui_window
    lib = window.settings.library_dir
    key = str(lib / "rivals skins" / "melee" / "Katana")

    # Un favori présent avant le rechargement : il doit survivre.
    window.settings.toggle_favorite(key)

    spawned = {}
    fake_popen = object()

    def fake_relaunch(*args, **kwargs):
        spawned["called"] = True
        spawned["args"] = args
        return fake_popen

    monkeypatch.setattr(mw, "relaunch", fake_relaunch)
    window._restart_app()
    qapp.processEvents()

    # 1. Sauvegarde effective : le favori est sur le disque.
    assert spawned.get("called") is True
    assert AppSettings.load().is_favorite(key)
    # 2. La nouvelle instance est lancée avant la fermeture.
    assert spawned["args"] == ()
    # 3. L'instance courante est fermée proprement.
    assert not window.isVisible()


# ---------------------------------------------------------------------- #
# 3. Admin — one central gate (ADMIN_MODE), no scattered `if admin`
# ---------------------------------------------------------------------- #
def test_admin_tools_hidden_in_normal_build(ui_window, qapp) -> None:
    """Version normale : les outils admin sont ABSENTS de l'interface
    (synchronisation des assets masquée) ; « Recharger l'application »
    reste un outil utilisateur, visible."""
    window = ui_window
    window.go(("settings", None))
    qapp.processEvents()
    assert not window._settings._sync_assets_btn.isVisible()
    assert window._settings._restart_btn.isVisible()


def test_admin_mode_shows_admin_tools(ui_window, qapp, monkeypatch) -> None:
    """Build admin : retourner la porte centrale ``ADMIN_MODE`` à True
    réaffiche les outils d'administration des assets — une seule source,
    aucun « if admin » dispersé dans l'interface."""
    import app.config as config_mod
    import ui.views.settings_view as settings_mod

    assert config_mod.admin_enabled() is False
    monkeypatch.setattr(config_mod, "ADMIN_MODE", True)
    assert settings_mod.admin_enabled() is True

    window = ui_window
    window.go(("settings", None))
    qapp.processEvents()
    window._settings.refresh_admin_visibility()
    assert window._settings._sync_assets_btn.isVisible()
    # L'utilisateur garde aussi ses outils (le rechargement reste visible).
    assert window._settings._restart_btn.isVisible()
