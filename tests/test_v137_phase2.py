"""Phase 2 (v1.3.7) — navigation reorder + verification & preferences.

Covers:

* the top bar is now three logical zones, in exact order:
      ← →  Corbeille  Profils   ACCUEIL   Favoris  [Recherche] 🔍  ⚙️
  (loupe right next to the search field, settings far right, profiles in
  the left cluster, favourites before the search block);
* no overlap at every window width (960 → 1920), nothing disappears,
  ACCUEIL stays visually central;
* preferences (language, theme, favourites, paths) survive a restart and
  a corrupted settings file never crashes the app (clean fallback);
* user validations survive a restart and a corrupted store never crashes;
* « Recharger l'application » still does a real restart and persists
  language, theme, favourites and paths before relaunching.
"""

from __future__ import annotations

import json
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


def _library(root: Path) -> Path:
    lib = root / "lib"
    _write_json(lib / "Charms" / "charm 0.json", {"replacement_rules": []})
    _write_json(lib / "rivals skins" / "Primary" / "Assault Rifle" / "skin 0.json",
                {"replacement_rules": []})
    _write_json(lib / "rivals skins" / "Primary" / "Assault Rifle" / "skin 1.json",
                {"replacement_rules": []})
    return lib


@pytest.fixture()
def appdata(tmp_path, monkeypatch) -> Path:
    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    lib = _library(tmp_path)
    fleasion = tmp_path / "fleasion"
    fleasion.mkdir(parents=True)
    (fleasion / "settings.json").write_text("{}", encoding="utf-8")
    sdir = appdata / "RivalsConfigManager"
    sdir.mkdir(parents=True)
    (sdir / "settings.json").write_text(
        json.dumps({"library_dir": str(lib), "fleasion_dir": str(fleasion),
                    "language": "fr"}),
        encoding="utf-8",
    )
    return appdata


@pytest.fixture()
def ui_window(qapp, appdata):
    from ui.main_window import MainWindow

    window = MainWindow()
    window.show()
    qapp.processEvents()
    yield window
    window.deleteLater()


def _mouse_nav(window, qapp, target) -> None:
    window.go(target)
    qapp.processEvents()


# ---------------------------------------------------------------------- #
# 1. Barre supérieure — ordre exact des trois zones
# ---------------------------------------------------------------------- #
def _top_bar_buttons(window):
    return {
        "back": window._back_btn,
        "forward": window._forward_btn,
        "trash": window._trash_btn,
        "profiles": window._profiles_btn,
        "title": window._top_title,
        "favorites": window._favorites_btn,
        "search": window._search,
        "loupe": window._search_page_btn,
        "add_weapon": window._add_weapon_btn,
        "settings": window._settings_btn,
    }


def test_top_bar_exact_order(ui_window, qapp) -> None:
    """Ordre exact demandé (Phase 2) : ← → Corbeille Profils | ACCUEIL |
    Favoris [Recherche] 🔍 | ⚙️ — la loupe juste après le champ."""
    window = ui_window
    window.resize(1280, 720)
    qapp.processEvents()
    btns = _top_bar_buttons(window)

    # Navigation gauche.
    assert btns["back"].x() < btns["forward"].x() < btns["trash"].x() < btns["profiles"].x()
    # Accueil central, après Profils et avant Favoris.
    assert btns["profiles"].x() + btns["profiles"].width() < btns["title"].x()
    assert btns["title"].x() + btns["title"].width() < btns["favorites"].x()
    # Outils droite : Favoris avant la recherche, loupe collée après le champ.
    assert btns["favorites"].x() + btns["favorites"].width() < btns["search"].x()
    assert btns["search"].x() + btns["search"].width() < btns["loupe"].x()
    assert btns["loupe"].x() + btns["loupe"].width() < btns["settings"].x()
    # Paramètres tout à droite, dans sa zone.
    assert btns["settings"].x() + btns["settings"].width() <= window.width()


def test_top_bar_presence_and_icons(ui_window, qapp) -> None:
    """Tous les boutons sont présents et leurs icônes ne sont pas vides."""
    window = ui_window
    for name, btn in _top_bar_buttons(window).items():
        if name in ("title", "search", "add_weapon"):
            continue
        assert btn.icon() is not None and not btn.icon().isNull(), name
    assert "Profils" in window._profiles_btn.text()
    # La loupe a bien son icône de recherche.
    assert not window._search_page_btn.icon().pixmap(20, 20).isNull()


def test_accueil_visually_central(ui_window, qapp) -> None:
    """À grande largeur, ACCUEIL est réellement centré : les espaces à
    gauche et à droite du titre sont équilibrés (deux stretchs égaux)."""
    window = ui_window
    window.resize(1920, 1080)
    qapp.processEvents()
    btns = _top_bar_buttons(window)
    gap_left = btns["title"].x() - (btns["profiles"].x() + btns["profiles"].width())
    gap_right = btns["favorites"].x() - (btns["title"].x() + btns["title"].width())
    assert gap_left >= 80 and gap_right >= 80, (gap_left, gap_right)
    assert abs(gap_left - gap_right) <= 4, (gap_left, gap_right)


# ---------------------------------------------------------------------- #
# 2. Responsive — aucun chevauchement sur toutes les largeurs
# ---------------------------------------------------------------------- #
def test_top_bar_no_overlap_all_widths(ui_window, qapp) -> None:
    """Aux largeurs 960/1024/1280/1366/1600/1920 : aucun chevauchement,
    aucun bouton ne disparaît, la loupe reste collée à la recherche,
    Paramètres reste à droite et Profils dans la zone gauche."""
    from app.scanner import find_node

    window = ui_window
    # Ouvrir une catégorie d'armes → le bouton « Ajouter une arme » est
    # visible et participe à la chaîne.
    primary = find_node(window.root_node, window.settings.library_dir / "rivals skins" / "Primary")
    _mouse_nav(window, qapp, ("browse", primary))

    for size in [(960, 640), (1024, 768), (1280, 720), (1366, 768), (1600, 900), (1920, 1080)]:
        window.resize(*size)
        qapp.processEvents()
        btns = _top_bar_buttons(window)

        # Chaîne visible complète, sans chevauchement (tolérance 1 px).
        chain = ["back", "forward", "trash", "profiles", "title",
                 "favorites", "search", "loupe", "add_weapon", "settings"]
        for left, right in zip(chain, chain[1:]):
            assert btns[left].x() + btns[left].width() <= btns[right].x() + 1, \
                f"{size}: {left} chevauche {right}"
        # Rien ne déborde à droite ni ne sort par la gauche.
        assert btns["settings"].x() + btns["settings"].width() <= window.width() + 1
        assert btns["back"].x() >= 0
        # Loupe toujours après le champ, Paramètres toujours à droite de tout.
        assert btns["search"].x() + btns["search"].width() < btns["loupe"].x()
        assert btns["settings"].x() > btns["loupe"].x() + btns["loupe"].width()
        # Profils reste dans la zone gauche (avant le titre central).
        assert btns["profiles"].x() + btns["profiles"].width() < btns["title"].x()


# ---------------------------------------------------------------------- #
# 3. Préférences — persistance et résilience
# ---------------------------------------------------------------------- #
def test_preferences_survive_restart(ui_window, qapp, appdata) -> None:
    """Langue, thème, favoris, bibliothèque et Fleasion : conservés après
    fermeture/réouverture (nouvelle instance)."""
    from ui.main_window import MainWindow

    window = ui_window
    lib = window.settings.library_dir
    skin = lib / "rivals skins" / "Primary" / "Assault Rifle" / "skin 0.json"

    window.settings.language = "en"
    window.settings.theme = "midnight"
    window.settings.toggle_favorite(str(skin))
    window.settings.save()

    window2 = MainWindow()
    window2.show()
    qapp.processEvents()

    assert window2.settings.language == "en"
    assert window2.settings.theme == "midnight"
    assert str(skin) in window2.settings.favorites
    assert window2.settings.library_dir == lib
    assert window2.settings.fleasion_dir == window.settings.fleasion_dir
    window2.deleteLater()


def test_corrupted_settings_falls_back_cleanly(appdata) -> None:
    """Un settings.json corrompu (JSON invalide OU de la mauvaise forme,
    ex. un tableau) ne provoque jamais de crash : fallback propre vers les
    défauts, puis sauvegarde fonctionnelle."""
    from app.config import AppSettings, settings_file

    settings_file().write_text("{ pas du json valide !", encoding="utf-8")
    s = AppSettings.load()  # ne doit pas lever
    assert s.language == "fr" or s.language  # une valeur par défaut valide
    assert s.favorites == []
    assert s.fleasion_dir is None and s.library_dir is None
    # La sauvegarde écrase proprement le fichier corrompu.
    s.language = "en"
    s.save()
    reloaded = AppSettings.load()
    assert reloaded.language == "en"

    # JSON valide mais de la mauvaise forme (tableau) : même fallback.
    settings_file().write_text("[1, 2, 3]", encoding="utf-8")
    s2 = AppSettings.load()  # ne doit pas lever
    assert s2.language and s2.favorites == []
    assert s2.language_chosen is False and s2.onboarding_completed is False


def test_corrupted_validations_store_falls_back_cleanly(appdata) -> None:
    """Un validations.json corrompu → aucune validation, jamais de crash ;
    la validation fonctionne ensuite normalement."""
    from app.config import data_dir
    from app.validations import ValidationStore

    path = data_dir() / "validations.json"
    path.write_text("{n'importe quoi", encoding="utf-8")
    store = ValidationStore()  # ne doit pas lever
    assert store.all() == {}
    store.set_validated("rivals skins/melee/Katana/Kirambit.json")
    assert store.is_validated("rivals skins/melee/Katana/Kirambit.json")
    assert ValidationStore().is_validated("rivals skins/melee/Katana/Kirambit.json")


def test_validations_survive_restart_and_reset(appdata) -> None:
    """La validation d'une configuration (identité = chemin stable, jamais
    le nom) persiste après redémarrage et peut être réinitialisée."""
    from app.validations import ValidationStore

    store = ValidationStore()
    key = "rivals skins/Melee/Katana/Kirambit.json"
    store.set_validated(key, name="Kirambit", rel_path="rivals skins/Melee/Katana/Kirambit")

    # Redémarrage : nouvelle instance du store, même fichier.
    reloaded = ValidationStore()
    assert reloaded.is_validated(key)
    assert reloaded.entry(key).name == "Kirambit"  # info seule, jamais la clé
    assert reloaded.entry(key).rel_path == "rivals skins/Melee/Katana/Kirambit"

    # Réinitialisation.
    assert reloaded.clear_validated(key)
    assert not ValidationStore().is_validated(key)


# ---------------------------------------------------------------------- #
# 4. Rechargement — vrai redémarrage, rien n'est perdu
# ---------------------------------------------------------------------- #
def test_restart_persists_everything_before_relaunch(ui_window, qapp, appdata, monkeypatch) -> None:
    """« Recharger l'application » : sauvegarde langue/thème/favoris/chemins,
    lance une nouvelle instance et ferme l'ancienne."""
    import ui.main_window as mw
    from app.config import settings_file

    window = ui_window
    lib = window.settings.library_dir
    skin = lib / "rivals skins" / "Primary" / "Assault Rifle" / "skin 1.json"

    window.settings.language = "en"
    window.settings.theme = "midnight"
    window.settings.toggle_favorite(str(skin))

    spawned = {}
    monkeypatch.setattr(mw, "relaunch",
                        lambda *a, **k: (spawned.update(called=True), object())[1])
    window._restart_app()
    qapp.processEvents()

    # La nouvelle instance a bien été demandée et l'ancienne fermée.
    assert spawned.get("called") is True
    assert not window.isVisible()

    # Tout est écrit sur disque avant la relance (relu au démarrage).
    data = json.loads(settings_file().read_text(encoding="utf-8"))
    assert data["language"] == "en"
    assert data["theme"] == "midnight"
    assert str(skin) in data["favorites"]
    assert data["library_dir"] == str(lib)
    assert data["fleasion_dir"] == str(window.settings.fleasion_dir)


def test_restart_command_independent_of_cwd(qapp, monkeypatch, tmp_path) -> None:
    """La commande de relance n'utilise ni le cwd ni System32 — elle part du
    vrai interpréteur et du chemin absolu du script."""
    import app.restart as restart

    script = str(tmp_path / "main.py")
    before = restart.relaunch_command(script)
    monkeypatch.chdir(tmp_path)
    after = restart.relaunch_command(script)
    assert before == after
    assert before[0]  # interpréteur réel
    assert before[1] == script  # chemin absolu du script
    assert "System32" not in " ".join(before).lower()
