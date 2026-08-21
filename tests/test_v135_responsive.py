"""v1.3.5 responsive + favourites-semantics regression tests.

The responsive bug: the favourite star (and the status chip) are absolutely
positioned overlays whose position was only recomputed on ``resizeEvent``
*while visible*. The grid sizes the cards before their page becomes the
visible stack widget, so the overlays kept their stale pre-layout position
(the star sat outside the card). Every card now re-lays out its own
overlays from its own size on resize AND on show — fully independent of the
other cards, whatever the window size.

The favourites semantics: a card represents a **usable element** (ConfigItem
— skin, charm, emote, FastFlag, texture pack, skybox — or a folder that
directly contains configurations, e.g. a weapon) → star; a **navigation
folder** (top-level category, Primary/Secondary/Melee/Utility, any folder
containing only folders) → no star.

Covers the mandatory list: config card with star, navigation card without,
skin/weapon/charm/pack/skybox with star, several rows, resize, fullscreen →
window and window → fullscreen, favourite add/remove after resize,
persistence, Texture & Skybox after resize (cards + images).
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

#: A valid 1×1 PNG used to give real preview images to texture packs.
PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
    "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)

SIZES = [
    (560, 420),      # petite fenêtre
    (800, 600),      # fenêtre moyenne
    (1080, 720),     # fenêtre moyenne/grande
    (1600, 1000),    # grande fenêtre
    (640, 480),      # retour à une petite fenêtre
]


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


def _full_library(root: Path) -> Path:
    """Bibliothèque couvrant toutes les situations du rapport : catégories
    de navigation, armes multi-lignes, skins, charms, emotes, FastFlags,
    packs et skyboxes (avec previews)."""
    lib = root / "lib"

    # Catégories de premier niveau : navigation pure (pas d'étoile).
    for cat in ("Charms", "emotes", "FastFlags", "Wraps", "Kill and hit sounds"):
        for i in range(5):
            _write_json(lib / cat / f"item {i}.json", {"replacement_rules": []})

    # Texture & Skybox : une catégorie avec dossiers de navigation, packs
    # (folder-configs avec preview.jpg) et skyboxes (fichiers).
    ts = lib / "Textures and skyboxes"
    _write_json(ts / "gun texture pack" / "crimvals.json", {"replacement_rules": []})
    (ts / "gun texture pack" / "preview.jpg").write_bytes(PNG_1PX)
    for i in range(3):
        pack = ts / "Texture packs" / f"pack {i}"
        _write_json(pack / "config.json", {"replacement_rules": []})
        (pack / "preview.jpg").write_bytes(PNG_1PX)
    for name in ("Classic Skybox", "cloudly sky", "heaven"):
        _write_json(ts / "Sky" / f"{name}.json", {"replacement_rules": []})
    # « Dark sky » contient UNIQUEMENT un sous-dossier → navigation pure.
    _write_json(ts / "Dark sky" / "Dark sky" / "Dark sky.json", {"replacement_rules": []})

    # Rivals skins : catégories (navigation) → armes (étoile) → skins.
    for cat in ("primary", "secondary", "melee", "utility"):
        for w in range(5):
            weapon = lib / "rivals skins" / cat / f"Weapon {w}"
            for s in range(6):  # 6 skins → plusieurs lignes de cartes
                _write_json(weapon / f"skin {s}.json", {"replacement_rules": []})
    return lib


@pytest.fixture()
def ui_window(qapp, tmp_path, monkeypatch):
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    lib = _full_library(tmp_path)
    fleasion = tmp_path / "fleasion"
    fleasion.mkdir(parents=True)
    settings_path = appdata / "RivalsConfigManager" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps({"library_dir": str(lib), "fleasion_dir": str(fleasion)}),
        encoding="utf-8",
    )
    (fleasion / "settings.json").write_text("{}", encoding="utf-8")
    window = MainWindow()
    window.show()
    qapp.processEvents()
    yield window
    window.deleteLater()


def _go(window, qapp, state) -> None:
    window.go(state)
    qapp.processEvents()


def _browse(window, qapp, path: Path):
    from app.scanner import find_node

    node = find_node(window.root_node, path)
    assert node is not None, f"nœud introuvable : {path}"
    window.go(("browse", node))
    qapp.processEvents()
    return node


def _card_in(window, qapp, path: Path):
    """Ouvrir la page du dossier parent puis retourner la carte de
    ``path`` (échec explicite si elle n'y est pas)."""
    _browse(window, qapp, path.parent)
    card = window._browse._grid.find_card(str(path))
    assert card is not None, f"carte manquante pour {path}"
    return card


def _resize(window, qapp, width: int, height: int) -> None:
    window.resize(width, height)
    qapp.processEvents()


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #
def _overlay_problems(cards) -> list[str]:
    """Chaque carte positionne ses propres overlays : aucune étoile ne doit
    être hors de sa carte, quelle que soit la taille de fenêtre."""
    problems: list[str] = []
    for card in cards:
        fav = card.favorite_button
        if fav is not None:
            if not fav.isVisible():
                problems.append(f"étoile invisible : {card.drag_key}")
                continue
            p = fav.pos()
            inside = (
                p.x() >= 0
                and p.y() >= 0
                and p.x() + fav.width() <= card.width()
                and p.y() + fav.height() <= card.height()
            )
            if not inside:
                problems.append(
                    f"étoile hors carte : {card.drag_key} "
                    f"(étoile {p.x()},{p.y()} / carte {card.width()}x{card.height()})"
                )
    return problems


def _assert_stars_inside(window, qapp, label: str) -> None:
    grid = window._current_grid()
    assert grid is not None, f"pas de grille courante ({label})"
    problems = _overlay_problems(grid._cards)
    assert not problems, f"{label} : {problems[:5]}"


def _assert_previews_ok(window, qapp, label: str) -> None:
    """Les previews des cartes restent présentes et dimensionnées après
    resize (jamais une carte vide, jamais une image qui ne réapparaît
    qu'en plein écran)."""
    grid = window._current_grid()
    assert grid is not None
    for card in grid._cards:
        preview = card._preview
        pixmap = preview.pixmap()
        assert pixmap is not None and not pixmap.isNull(), (
            f"preview manquante : {card.drag_key} ({label})"
        )
        size = preview.size()
        assert size.width() > 1 and size.height() > 1, (
            f"preview de taille nulle : {card.drag_key} ({label})"
        )


# ---------------------------------------------------------------------- #
# 1. Sémantique des étoiles (Node navigation vs ConfigItem utilisable)
# ---------------------------------------------------------------------- #
def test_config_card_has_star(ui_window, qapp) -> None:
    window = ui_window
    lib = window.settings.library_dir
    skin = _card_in(window, qapp, lib / "rivals skins" / "primary" / "Weapon 0" / "skin 0.json")
    assert skin.favorite_button is not None and skin.favorite_button.isVisible()


def test_navigation_card_has_no_star(ui_window, qapp) -> None:
    window = ui_window
    lib = window.settings.library_dir

    # Grandes catégories de l'accueil.
    _go(window, qapp, ("home", None))
    for category in ("rivals skins", "Charms", "emotes", "FastFlags",
                     "Textures and skyboxes", "Wraps", "Kill and hit sounds"):
        card = window._home._grid.find_card(str(lib / category))
        assert card is not None, f"catégorie manquante : {category}"
        assert card.favorite_button is None, f"étoile en trop sur {category}"

    # Catégories d'armes.
    _browse(window, qapp, lib / "rivals skins")
    for category in ("primary", "secondary", "melee", "utility"):
        card = _card_in(window, qapp, lib / "rivals skins" / category)
        assert card.favorite_button is None, f"étoile en trop sur {category}"


def test_weapon_has_star(ui_window, qapp) -> None:
    window = ui_window
    lib = window.settings.library_dir
    _browse(window, qapp, lib / "rivals skins" / "melee")
    card = _card_in(window, qapp, lib / "rivals skins" / "melee" / "Weapon 1")
    assert card.favorite_button is not None and card.favorite_button.isVisible()


def test_skin_has_star(ui_window, qapp) -> None:
    window = ui_window
    lib = window.settings.library_dir
    card = _card_in(window, qapp, lib / "rivals skins" / "melee" / "Weapon 1" / "skin 3.json")
    assert card.favorite_button is not None and card.favorite_button.isVisible()


def test_charm_has_star(ui_window, qapp) -> None:
    window = ui_window
    lib = window.settings.library_dir
    card = _card_in(window, qapp, lib / "Charms" / "item 1.json")
    assert card.favorite_button is not None and card.favorite_button.isVisible()


def test_texture_pack_has_star(ui_window, qapp) -> None:
    window = ui_window
    lib = window.settings.library_dir
    # Le pack est une folder-configuration : sa carte est identifiée par le
    # chemin du DOSSIER (jamais par config.json).
    card = _card_in(window, qapp, lib / "Textures and skyboxes" / "Texture packs" / "pack 0")
    assert card.favorite_button is not None and card.favorite_button.isVisible()


def test_skybox_has_star(ui_window, qapp) -> None:
    window = ui_window
    lib = window.settings.library_dir
    card = _card_in(window, qapp, lib / "Textures and skyboxes" / "Sky" / "Classic Skybox.json")
    assert card.favorite_button is not None and card.favorite_button.isVisible()


# ---------------------------------------------------------------------- #
# 2. Responsive — plusieurs lignes, resize, plein écran
# ---------------------------------------------------------------------- #
def test_multi_row_grid_every_star_inside(ui_window, qapp) -> None:
    """Plusieurs lignes de cartes : l'étoile de CHAQUE ligne reste dans sa
    carte (une arme avec 30 skins → beaucoup de lignes)."""
    window = ui_window
    lib = window.settings.library_dir
    _browse(window, qapp, lib / "rivals skins" / "primary" / "Weapon 0")
    assert len(window._browse._grid._cards) == 6
    for width, height in SIZES:
        _resize(window, qapp, width, height)
        _assert_stars_inside(window, qapp, f"multi-row {width}x{height}")


def test_resize_sequence_keeps_stars(ui_window, qapp) -> None:
    """Plusieurs changements successifs de taille (petit → moyen → grand →
    petit → moyen...) : aucune étoile ne sort de sa carte, aucun contrôle
    ne disparaît."""
    window = ui_window
    lib = window.settings.library_dir
    _browse(window, qapp, lib / "Textures and skyboxes" / "Texture packs")
    for _ in range(2):
        for width, height in SIZES:
            _resize(window, qapp, width, height)
            _assert_stars_inside(window, qapp, f"resize {width}x{height}")
            _assert_previews_ok(window, qapp, f"resize {width}x{height}")


def test_fullscreen_window_transitions_keep_stars(ui_window, qapp) -> None:
    """Plein écran → fenêtre → plein écran → fenêtre : les étoiles restent
    dans leurs cartes à chaque transition (petite et grande fenêtre)."""
    window = ui_window
    lib = window.settings.library_dir
    _browse(window, qapp, lib / "rivals skins" / "secondary" / "Weapon 2")

    window.showFullScreen()
    qapp.processEvents()
    _assert_stars_inside(window, qapp, "fullscreen 1")

    window.showNormal()
    _resize(window, qapp, 1080, 720)
    _assert_stars_inside(window, qapp, "fenêtre après plein écran")

    window.showFullScreen()
    qapp.processEvents()
    _assert_stars_inside(window, qapp, "fullscreen 2")

    window.showNormal()
    _resize(window, qapp, 640, 480)
    _assert_stars_inside(window, qapp, "petite fenêtre après plein écran")


def test_small_window_many_rows(ui_window, qapp) -> None:
    """Petite fenêtre + beaucoup de cartes : la première ligne comme les
    lignes suivantes gardent leurs contrôles (étoile dans la carte)."""
    window = ui_window
    lib = window.settings.library_dir
    _browse(window, qapp, lib / "Textures and skyboxes" / "Texture packs")
    _resize(window, qapp, 560, 420)
    _assert_stars_inside(window, qapp, "petite fenêtre packs")
    _resize(window, qapp, 480, 400)
    _assert_stars_inside(window, qapp, "très petite fenêtre packs")


def test_favorite_toggle_after_resize(ui_window, qapp) -> None:
    """Ajout/retrait d'un favori APRÈS plusieurs redimensionnements : la
    carte reste cliquable, la position de l'étoile reste correcte."""
    window = ui_window
    lib = window.settings.library_dir
    skin_path = lib / "rivals skins" / "primary" / "Weapon 0" / "skin 1.json"
    _browse(window, qapp, lib / "rivals skins" / "primary" / "Weapon 0")
    for width, height in SIZES:
        _resize(window, qapp, width, height)

    card = window._browse._grid.find_card(str(skin_path))
    assert card is not None and card.favorite_button is not None
    card.favorite_button.click()
    qapp.processEvents()
    assert window.settings.is_favorite(str(skin_path))
    assert card.is_favorite()

    # Encore un resize : l'étoile pleine reste dans la carte.
    _resize(window, qapp, 800, 600)
    _assert_stars_inside(window, qapp, "favori après resize")

    # Retrait après resize.
    card.favorite_button.click()
    qapp.processEvents()
    assert not window.settings.is_favorite(str(skin_path))


def test_favorite_persists_after_restart(ui_window, qapp, tmp_path, monkeypatch) -> None:
    from app.scanner import find_node
    from ui.main_window import MainWindow

    window = ui_window
    lib = window.settings.library_dir
    skin_path = lib / "rivals skins" / "primary" / "Weapon 0" / "skin 1.json"
    _browse(window, qapp, lib / "rivals skins" / "primary" / "Weapon 0")
    _resize(window, qapp, 640, 480)
    card = window._browse._grid.find_card(str(skin_path))
    card.favorite_button.click()
    qapp.processEvents()
    assert window.settings.is_favorite(str(skin_path))

    window2 = MainWindow()
    window2.show()
    qapp.processEvents()
    assert str(skin_path) in window2.settings.favorites
    folder = find_node(window2.root_node, skin_path.parent)
    window2.go(("browse", folder))
    qapp.processEvents()
    restored = window2._browse._grid.find_card(str(skin_path))
    assert restored is not None and restored.is_favorite()
    assert restored.favorite_button.isVisible()
    window2.deleteLater()


# ---------------------------------------------------------------------- #
# 3. Texture & Skybox après resize (cartes + images)
# ---------------------------------------------------------------------- #
def test_texture_skybox_after_resize(ui_window, qapp) -> None:
    """Texture & Skybox : la page (packs, skyboxes) garde ses étoiles dans
    les cartes à chaque taille ; le dossier de navigation « Dark sky »
    (sous-dossier uniquement) n'a pas d'étoile ; l'ouverture fonctionne."""
    window = ui_window
    lib = window.settings.library_dir
    _browse(window, qapp, lib / "Textures and skyboxes")

    # Navigation pure : « Dark sky » ne contient qu'un sous-dossier → pas
    # d'étoile. Les vrais contenus (Sky, Texture packs, gun texture pack)
    # ont des étoiles.
    dark = _card_in(window, qapp, lib / "Textures and skyboxes" / "Dark sky")
    assert dark.favorite_button is None, "étoile en trop sur le dossier Dark sky"
    for usable in ("Sky", "Texture packs", "gun texture pack"):
        card = _card_in(window, qapp, lib / "Textures and skyboxes" / usable)
        assert card.favorite_button is not None, f"étoile manquante sur {usable}"

    for width, height in SIZES:
        _resize(window, qapp, width, height)
        _assert_stars_inside(window, qapp, f"T&S {width}x{height}")

    # Ouverture : cliquer « Texture packs » ouvre sa page (cartes packs).
    packs = _card_in(window, qapp, lib / "Textures and skyboxes" / "Texture packs")
    packs.clicked.emit()
    qapp.processEvents()
    assert window._stack.currentWidget() is window._browse
    assert window._history.current()[1].path == lib / "Textures and skyboxes" / "Texture packs"
    for width, height in SIZES:
        _resize(window, qapp, width, height)
        _assert_stars_inside(window, qapp, f"packs {width}x{height}")


def test_texture_skybox_images_after_resize(ui_window, qapp) -> None:
    """Les images des packs Texture & Skybox (preview.jpg) restent
    affichées et correctement redimensionnées après chaque resize — jamais
    une carte vide, jamais une image qui n'apparaît qu'en plein écran."""
    window = ui_window
    lib = window.settings.library_dir
    _browse(window, qapp, lib / "Textures and skyboxes" / "Texture packs")
    _assert_previews_ok(window, qapp, "initial")
    for width, height in SIZES:
        _resize(window, qapp, width, height)
        _assert_previews_ok(window, qapp, f"images {width}x{height}")

    window.showFullScreen()
    qapp.processEvents()
    _assert_previews_ok(window, qapp, "images plein écran")
    window.showNormal()
    _resize(window, qapp, 800, 600)
    _assert_previews_ok(window, qapp, "images retour fenêtre")
