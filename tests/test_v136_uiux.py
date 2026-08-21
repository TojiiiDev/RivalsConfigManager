"""v1.3.6 UI/UX phase tests.

Covers the UI rework without touching the stable systems:

* the drop zone is large, self-explanatory (icon + title + subtitle),
  with normal / hover / drag-over states, drag & drop unchanged, and a
  click-to-browse action that reuses the EXACT same import flow as a drop;
* the secondary Settings button (next to the drop zone) is gone, the main
  one stays top-right;
* the Profiles button is explicit (icon + « Profils » text) and navigates;
* preferences (theme, language, favourites, paths) persist across restart;
* regressions: favourites, Texture & Skybox, search, restart.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QFileDialog


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


def _library(root: Path) -> Path:
    lib = root / "lib"
    # Catégorie de navigation (pas d'étoile) contenant des charms.
    for i in range(3):
        _write_json(lib / "Charms" / f"charm {i}.json", {"replacement_rules": []})
    # Pack Texture & Skybox (folder-config → étoile).
    _write_json(lib / "Textures and skyboxes" / "gun texture pack" / "crimvals.json",
                {"replacement_rules": []})
    # Rivals skins : catégorie → arme → skins.
    for s in range(4):
        _write_json(lib / "rivals skins" / "primary" / "Assault Rifle" / f"skin {s}.json",
                    {"replacement_rules": []})
    return lib


@pytest.fixture()
def ui_window(qapp, tmp_path, monkeypatch):
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    lib = _library(tmp_path)
    fleasion = tmp_path / "fleasion"
    fleasion.mkdir(parents=True)
    settings_path = appdata / "RivalsConfigManager" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps({"library_dir": str(lib), "fleasion_dir": str(fleasion),
                    "language": "fr"}),
        encoding="utf-8",
    )
    (fleasion / "settings.json").write_text("{}", encoding="utf-8")
    window = MainWindow()
    window.show()
    qapp.processEvents()
    yield window
    window.deleteLater()


def _mouse_click(widget, qapp, x: float = 10, y: float = 10) -> None:
    press = QMouseEvent(QEvent.MouseButtonPress, QPointF(x, y), QPointF(x, y),
                        Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)
    release = QMouseEvent(QEvent.MouseButtonRelease, QPointF(x, y), QPointF(x, y),
                          Qt.LeftButton, Qt.NoButton, Qt.NoModifier)
    widget.mousePressEvent(press)
    widget.mouseReleaseEvent(release)
    qapp.processEvents()


# ---------------------------------------------------------------------- #
# 1. Zone de dépôt — grande, explicite, drag & drop + clic
# ---------------------------------------------------------------------- #
def test_drop_zone_explicit_texts_and_states(ui_window, qapp) -> None:
    """La zone de dépôt est grande et explicite : icône + titre + sous-texte,
    état drag-over activé/relâché, pas de régression du drop."""
    from PySide6.QtCore import QMimeData, QPoint, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent

    window = ui_window
    zone = window._home._drop_zone

    assert zone.acceptDrops()
    assert zone.height() >= 70, "la zone de dépôt doit être grande"
    assert zone.width() >= 400, "la zone de dépôt doit occuper la largeur"
    assert "Glissez-déposez vos fichiers ici" in zone._title.text()
    assert "cliquer pour parcourir vos fichiers" in zone._subtitle.text()
    assert not zone._icon.pixmap().isNull()

    # Drag-over : état visuel clair ; sortie : retour à la normale.
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(Path.home() / "mod.zip"))])
    drag = QDragEnterEvent(QPoint(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    zone.dragEnterEvent(drag)
    assert drag.isAccepted()
    assert zone.property("drag") is True
    leave = QDragLeaveEvent()
    zone.dragLeaveEvent(leave)
    assert zone.property("drag") is False

    # Dépôt : le signal part avec les fichiers locaux uniquement.
    captured = []
    zone.files_dropped.connect(captured.append)
    drop_mime = QMimeData()
    drop_mime.setUrls([
        QUrl.fromLocalFile(str(Path.home() / "a.json")),
        QUrl("https://example.com/remote.png"),  # jamais un fichier distant
    ])
    from PySide6.QtGui import QDropEvent

    drop = QDropEvent(QPointF(10, 10), Qt.CopyAction, drop_mime, Qt.LeftButton, Qt.NoModifier)
    zone.dropEvent(drop)
    qapp.processEvents()
    assert captured == [[Path.home() / "a.json"]]


def test_drop_zone_click_opens_browser_same_import_flow(ui_window, qapp, monkeypatch) -> None:
    """Clic sur la zone de dépôt → navigateur de fichiers → le flux d'import
    EXACTEMENT identique au glisser-déposer (jamais un second système)."""
    window = ui_window
    zone = window._home._drop_zone

    picked = [str(Path.home() / "pack.zip"), str(Path.home() / "skin.json")]
    monkeypatch.setattr(
        QFileDialog, "getOpenFileNames",
        staticmethod(lambda *a, **k: (picked, "")),
    )
    calls = []
    window._start_batch_import = lambda p: calls.append(p)  # type: ignore[method-assign]

    _mouse_click(zone, qapp)
    qapp.processEvents()
    # Le clic et le glisser-déposer passent par le MÊME pipeline d'import.
    assert calls == [[Path.home() / "pack.zip", Path.home() / "skin.json"]]


def test_home_secondary_settings_button_removed(ui_window, qapp) -> None:
    """Le bouton Paramètres secondaire (près de la zone de dépôt) a disparu ;
    le bouton principal reste en haut à droite et ouvre les Paramètres."""
    window = ui_window
    assert not hasattr(window._home, "_settings_btn"), "bouton Paramètres secondaire à supprimer"
    assert window._settings_btn is not None
    assert not window._settings_btn.icon().isNull()
    assert not window._settings_btn.icon().pixmap(22, 22).isNull()

    window._settings_btn.click()
    qapp.processEvents()
    assert window._stack.currentWidget() is window._settings


# ---------------------------------------------------------------------- #
# 2. Bouton Profils — explicite (icône + texte)
# ---------------------------------------------------------------------- #
def test_profiles_button_labeled_and_navigates(ui_window, qapp) -> None:
    window = ui_window
    btn = window._profiles_btn
    assert "Profils" in btn.text()
    assert not btn.icon().isNull()

    btn.click()
    qapp.processEvents()
    assert window._stack.currentWidget() is window._profiles_view
    assert window._profiles_view is not None


# ---------------------------------------------------------------------- #
# 3. Zone de dépôt + redimensionnement
# ---------------------------------------------------------------------- #
def test_drop_zone_survives_resize(ui_window, qapp) -> None:
    """Après redimensionnement, la zone de dépôt reste grande, lisible et
    la grille de cartes continue de fonctionner (aucune régression)."""
    window = ui_window
    zone = window._home._drop_zone
    for size in [(560, 420), (1080, 720), (1600, 1000), (800, 600)]:
        window.resize(*size)
        qapp.processEvents()
        assert zone.height() >= 70
        assert zone.isVisible()
        assert "Glissez-déposez vos fichiers ici" in zone._title.text()


# ---------------------------------------------------------------------- #
# 4. Préférences — persistance après redémarrage
# ---------------------------------------------------------------------- #
def test_preferences_persist_across_restart(ui_window, qapp, tmp_path, monkeypatch) -> None:
    """Langue, thème, favori et chemins configurés une fois → conservés
    après fermeture/réouverture (nouvelle instance)."""
    from app.scanner import find_node
    from ui.main_window import MainWindow

    window = ui_window
    lib = window.settings.library_dir

    # 1. Configurer : langue EN, thème midnight, un favori (skin).
    window.settings.language = "en"
    window.settings.theme = "midnight"
    skin = lib / "rivals skins" / "primary" / "Assault Rifle" / "skin 0.json"
    window.settings.toggle_favorite(str(skin))
    window.settings.save()

    # 2. Redémarrage (nouvelle instance).
    window2 = MainWindow()
    window2.show()
    qapp.processEvents()

    assert window2.settings.language == "en"
    assert window2.settings.theme == "midnight"
    assert str(skin) in window2.settings.favorites
    assert window2.settings.library_dir == lib
    assert window2.settings.fleasion_dir == window.settings.fleasion_dir
    # L'interface reflète la langue persistée (zone de dépôt retraduite).
    assert "Drag and drop your files here" in window2._home._drop_zone._title.text()
    # La carte du skin favori est restaurée avec son étoile pleine.
    folder = find_node(window2.root_node, skin.parent)
    window2.go(("browse", folder))
    qapp.processEvents()
    card = window2._browse._grid.find_card(str(skin))
    assert card is not None and card.is_favorite()
    window2.deleteLater()


# ---------------------------------------------------------------------- #
# 5. Régression — favoris, Texture & Skybox, recherche, Recharger
# ---------------------------------------------------------------------- #
def test_favorites_and_texture_skybox_still_work(ui_window, qapp) -> None:
    """Aucune régression : pack Texture & Skybox étoilé, catégorie de
    navigation sans étoile, ajout favori → vue Favoris, persistance."""
    from app.scanner import find_node
    from ui.main_window import PAGE_FAVORITES

    window = ui_window
    lib = window.settings.library_dir
    pack_path = lib / "Textures and skyboxes" / "gun texture pack"

    # Catégorie de navigation de l'accueil : pas d'étoile.
    ts_card = window._home._grid.find_card(str(lib / "Textures and skyboxes"))
    assert ts_card is not None and ts_card.favorite_button is None

    # Le pack (folder-config) porte l'étoile et se favorise.
    ts = find_node(window.root_node, lib / "Textures and skyboxes")
    window.go(("browse", ts))
    qapp.processEvents()
    pack_card = window._browse._grid.find_card(str(pack_path))
    assert pack_card is not None and pack_card.favorite_button is not None
    pack_card.favorite_button.click()
    qapp.processEvents()
    assert window.settings.is_favorite(str(pack_path))

    # La vue Favoris montre le pack ; le fichier reste en place.
    window.go((PAGE_FAVORITES, None))
    qapp.processEvents()
    assert window._favorites_view._grid.find_card(str(pack_path)) is not None
    assert pack_path.is_dir() and (pack_path / "crimvals.json").exists()


def test_search_page_still_works(ui_window, qapp) -> None:
    """La recherche dédiée fonctionne toujours (page + résultats + étoile)."""
    window = ui_window
    window._search_page_btn.click()
    qapp.processEvents()
    sv = window._search_view
    sv.set_query("charm")
    window._run_search()
    qapp.processEvents()
    cards = sv._grid._cards
    assert len(cards) >= 1
    assert all(card.favorite_button is not None for card in cards)


def test_restart_button_still_functional(ui_window, qapp, monkeypatch) -> None:
    """Le bouton « Recharger l'application » reste présent et déclenche la
    relance (sauvegarde + nouvelle instance) — logique intacte."""
    import ui.main_window as mw

    window = ui_window
    window.go(("settings", None))
    qapp.processEvents()
    btn = window._settings._restart_btn
    assert btn.isVisible()

    spawned = {}
    monkeypatch.setattr(mw, "relaunch", lambda *a, **k: (spawned.update(called=True), object())[1])
    window._restart_app()
    qapp.processEvents()
    assert spawned.get("called") is True
    assert not window.isVisible()
