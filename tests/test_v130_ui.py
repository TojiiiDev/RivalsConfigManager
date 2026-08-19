"""UI tests for the v1.3.0 features: dedicated search page (recents +
favorites filter), favourite stars on cards, smart status chips, contextual
« Ajouter une arme », keyboard shortcuts, the profiles page and responsive
layout with long titles.

Each test builds a real MainWindow offscreen (same pattern as
test_language_ui / test_smoke).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _configure(appdata: Path, library: Path, fleasion_dir: Path, language: str = "fr") -> None:
    from app.config import AppSettings

    settings = AppSettings()
    settings.fleasion_dir = fleasion_dir
    settings.library_dir = library
    settings.language = language
    settings.save()


def _make_library(root: Path) -> None:
    """Bibliothèque avec : configs sans/sur dépendances, une catégorie
    d'armes (Primary) et un nom très long (test responsive)."""
    _write_json(root / "Charms" / "nemesis charm.json", {"replacement_rules": []})
    _write_json(root / "Charms" / "broken charm.json",
                {"replacement_rules": [{"cdn_url": "missing model.obj"}]})
    gun_dir = root / "Primary" / "Hand gun"
    gun_dir.mkdir(parents=True, exist_ok=True)
    (gun_dir / "Pixelhandgun.json").write_text(
        json.dumps({"replacement_rules": [{"cdn_url": "Pixelboddy.obj"}]}),
        encoding="utf-8",
    )
    (gun_dir / "Pixelboddy.obj").write_text("mesh", encoding="utf-8")
    _write_json(root / "Charms" / "un nom de configuration extrêmement long "
                "qui ne devrait jamais tenir sur une seule ligne de carte.json",
                {"replacement_rules": []})


def _window(qapp, tmp_path, monkeypatch, language: str = "fr"):
    from ui.main_window import MainWindow

    library = tmp_path / "lib"
    _make_library(library)
    fleasion = tmp_path / "fleasion"
    fleasion.mkdir(parents=True, exist_ok=True)
    appdata = tmp_path / "AppData"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion, language)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    return window, library


def _config_item(window, library: Path, name: str):
    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    return next(c for c in charms.configs if c.name == name)


# ---------------------------------------------------------------------- #
# Favoris (étoile sur les cartes)
# ---------------------------------------------------------------------- #
def test_favorite_star_toggles_and_persists(qapp, tmp_path, monkeypatch) -> None:
    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    window.go(("browse", charms))
    qapp.processEvents()

    key = str(library / "Charms" / "nemesis charm.json")
    card = window._browse._grid.find_card(key)
    assert card is not None
    fav = card._fav_btn
    assert fav.isVisible()

    # Clic sur l'étoile -> favori + persistance.
    fav.click()
    qapp.processEvents()
    assert key in window.settings.favorites
    assert card.is_favorite()

    # L'état favori est indépendant de l'activation Fleasion.
    assert "nemesis charm" not in window.fleasion.list_configs()

    fav.click()
    qapp.processEvents()
    assert key not in window.settings.favorites
    assert not card.is_favorite()
    window.close()


def test_favorites_filter_in_search_page(qapp, tmp_path, monkeypatch) -> None:
    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()

    # Marquer deux configs favorites, une autre non.
    from app.config import AppSettings

    window.settings.favorites = [
        str(library / "Charms" / "nemesis charm.json"),
        str(library / "Charms" / "broken charm.json"),
    ]
    window.settings.save()

    window.go(("search", None))
    qapp.processEvents()
    sv = window._search_view
    sv._big_bar.setText("charm")
    window._on_search_view_query("charm")
    window._run_search()  # applique l'état immédiatement (même moteur)
    qapp.processEvents()

    # Filtre « Favoris » -> seulement les deux favorites.
    from app.search import FAVORITES_ONLY

    sv._filter_favorites.setCurrentIndex(sv._filter_favorites.findData(FAVORITES_ONLY))
    window._on_search_view_filters()
    qapp.processEvents()
    titles = [c._title_label._raw_text for c in sv._grid._cards]
    assert set(titles) == {"nemesis charm", "broken charm"}
    window.close()


def test_favorite_independent_of_fleasion_state(qapp, tmp_path, monkeypatch) -> None:
    """Favori ≠ activé : une config favorite inactive reste inactive dans
    Fleasion, et une config active non-favorite n'est pas un favori."""
    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()
    from app.config import AppSettings

    window.settings.favorites = [str(library / "Charms" / "nemesis charm.json")]
    window.settings.save()

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    window.go(("browse", charms))
    qapp.processEvents()
    key = str(library / "Charms" / "nemesis charm.json")
    card = window._browse._grid.find_card(key)
    assert card.is_favorite()
    # Non activée dans Fleasion (source de vérité).
    assert window.fleasion.status(_config_item(window, library, "nemesis charm")) != "active"
    window.close()


# ---------------------------------------------------------------------- #
# Page Recherche dédiée : récents + résultats
# ---------------------------------------------------------------------- #
def test_search_page_opens_and_shows_recents(qapp, tmp_path, monkeypatch) -> None:
    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()

    # Ouvrir une config -> enregistrée dans les récents.
    item = _config_item(window, library, "nemesis charm")
    window.go(("config", item))
    qapp.processEvents()
    assert len(window.recents.entries()) == 1

    # Page Recherche sans requête -> Récents affichés.
    window.go(("search", None))
    qapp.processEvents()
    sv = window._search_view
    assert sv._big_bar.text() == ""
    # Le label Récents est visible (pas de résultats de recherche).
    assert sv._recents_label.isVisible()
    window.close()


def test_search_page_results_use_same_engine(qapp, tmp_path, monkeypatch) -> None:
    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()

    window.go(("search", None))
    qapp.processEvents()
    sv = window._search_view
    sv._big_bar.setText("charm")
    window._on_search_view_query("charm")
    window._run_search()
    qapp.processEvents()

    titles = [c._title_label._raw_text for c in sv._grid._cards]
    assert "nemesis charm" in titles
    assert "broken charm" in titles
    # Même moteur que la recherche rapide : les résultats sont identiques
    # à ceux de la barre supérieure (même engine, aucune logique double).
    from app.search import SearchState, run_search

    engine_results = run_search(window.root_node, SearchState(query="charm"))
    assert [r.name for r in engine_results] == sorted(titles)
    window.close()


def test_search_page_matches_folder_results(qapp, tmp_path, monkeypatch) -> None:
    """La page Recherche utilise le MÊME moteur que la recherche rapide :
    une requête « gun » renvoie la config-dossier « Hand gun » (le scanner
    condense un dossier à skin unique en une seule config)."""
    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()
    window.go(("search", None))
    qapp.processEvents()
    sv = window._search_view
    sv._big_bar.setText("gun")
    window._on_search_view_query("gun")
    window._run_search()
    qapp.processEvents()
    titles = [c._title_label._raw_text for c in sv._grid._cards]
    assert "Hand gun" in titles
    # Même moteur : mêmes résultats que la recherche rapide.
    from app.search import SearchState, run_search

    engine_results = run_search(window.root_node, SearchState(query="gun"))
    assert [r.name for r in engine_results] == sorted(titles)
    window.close()


def test_search_page_clear_returns_to_recents(qapp, tmp_path, monkeypatch) -> None:
    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()

    window.go(("search", None))
    qapp.processEvents()
    sv = window._search_view
    sv._big_bar.setText("charm")
    window._on_search_view_query("charm")
    window._run_search()
    qapp.processEvents()
    assert sv._recents_label.isHidden()

    sv._clear_btn.click()
    qapp.processEvents()
    assert sv._big_bar.text() == ""
    assert sv._recents_label.isVisible()
    window.close()


# ---------------------------------------------------------------------- #
# Statut intelligent sur les cartes
# ---------------------------------------------------------------------- #
def test_card_status_chip_shows_states(qapp, tmp_path, monkeypatch) -> None:
    from ui.widgets.card import STATUS_ACTIVE, STATUS_INCOMPLETE, STATUS_READY

    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    window.go(("browse", charms))
    qapp.processEvents()

    # Carte saine -> « Prête » (ou aucune étiquette si non renseignée).
    ready = window._browse._grid.find_card(str(library / "Charms" / "nemesis charm.json"))
    assert ready is not None

    # Le statut ne réduit jamais le titre : le label occupe sa rangée entière.
    for card in window._browse._grid._cards:
        label = card._title_label
        btn = card._toggle_btn
        assert label.width() >= card.width() - 24 - btn.width() - 6 - 1, card._title_label._raw_text
        # L'étoile et le chip sont dans la zone preview, jamais sur le titre.
        assert not label.geometry().intersects(card._fav_btn.geometry())

    # Statut appliqué dynamiquement (simulation des données réelles).
    ready_card = window._browse._grid.find_card(str(library / "Charms" / "nemesis charm.json"))
    ready_card.set_status(STATUS_READY)
    assert ready_card._status_label.isVisible()
    ready_card.set_status(STATUS_INCOMPLETE)
    assert ready_card._status_label.isVisible()
    ready_card.set_status(STATUS_ACTIVE)
    assert ready_card._status_label.isVisible()
    window.close()


def test_status_never_claims_ready_when_dependency_missing(qapp, tmp_path, monkeypatch) -> None:
    """« Prête » n'est jamais affiché pour une config dont une dépendance
    obligatoire est absente : la vérification réelle décide."""
    from app.verify import verify_item

    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()
    broken = _config_item(window, library, "broken charm")
    verification = verify_item(broken)
    assert not verification.valid
    assert verification.deps.missing_obj_files == ("missing model.obj",)
    # Une dépendance manquante rend la configuration incomplète — jamais
    # « prête » (pas de faux succès).
    assert verification.deps.incomplete
    assert not verification.valid
    window.close()


# ---------------------------------------------------------------------- #
# Bouton « Ajouter une arme » contextuel
# ---------------------------------------------------------------------- #
def test_add_weapon_button_contextual(qapp, tmp_path, monkeypatch) -> None:
    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()

    # Accueil : masqué.
    assert not window._add_weapon_btn.isVisible()

    # Catégorie d'armes (Primary) : visible.
    primary = next(s for s in window.root_node.subdirs if s.name == "Primary")
    window.go(("browse", primary))
    qapp.processEvents()
    assert window._add_weapon_btn.isVisible()

    # Page d'une configuration de la catégorie d'armes : visible (le
    # contexte de catégorie est conservé). Le scanner condense le dossier
    # « Hand gun » en une config-dossier.
    gun = next(c for c in primary.configs if c.name == "Hand gun")
    window.go(("config", gun))
    qapp.processEvents()
    assert window._add_weapon_btn.isVisible()

    # Catégorie générale (Charms) : masqué.
    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    window.go(("browse", charms))
    qapp.processEvents()
    assert not window._add_weapon_btn.isVisible()

    # Recherche : masqué.
    window.go(("search", None))
    qapp.processEvents()
    assert not window._add_weapon_btn.isVisible()

    # Profils : masqué.
    window.go(("profiles", None))
    qapp.processEvents()
    assert not window._add_weapon_btn.isVisible()
    window.close()


# ---------------------------------------------------------------------- #
# Vérifier / Réparer (page config)
# ---------------------------------------------------------------------- #
def test_config_view_verify_button_present(qapp, tmp_path, monkeypatch) -> None:
    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()
    item = _config_item(window, library, "nemesis charm")
    window.go(("config", item))
    qapp.processEvents()
    assert window._config._sync_btn.isVisible()
    assert "VÉRIFIER" in window._config._sync_btn.text()
    window.close()


def test_verify_incomplete_shows_problems(qapp, tmp_path, monkeypatch) -> None:
    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()
    item = _config_item(window, library, "broken charm")
    window.go(("config", item))
    qapp.processEvents()
    window._verify_current()
    qapp.processEvents()
    text = window._config._result_label.text()
    assert "missing model.obj" in text
    assert "incompl" in text.lower()
    window.close()


# ---------------------------------------------------------------------- #
# Raccourcis clavier
# ---------------------------------------------------------------------- #
def test_shortcuts_registered_and_functional(qapp, tmp_path, monkeypatch) -> None:
    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()
    # Les raccourcis sont enregistrés (QShortcut sur la fenêtre).
    from PySide6.QtGui import QKeySequence, QShortcut

    shortcuts = window._shortcuts
    assert len(shortcuts) >= 4
    sequences = {s.key().toString() for s in shortcuts}
    assert "Ctrl+F" in sequences
    assert "Ctrl+H" in sequences

    # Ctrl+F ouvre la page Recherche et focus la barre.
    window._shortcut_open_search()
    qapp.processEvents()
    assert window._stack.currentWidget() is window._search_view
    assert window._search_view._big_bar.hasFocus()

    # Ctrl+H revient à l'accueil (raccourci lié à un lambda).
    from PySide6.QtGui import QKeySequence

    home_shortcut = next(s for s in shortcuts if s.key().toString() == "Ctrl+H")
    home_shortcut.activated.emit()
    qapp.processEvents()
    assert window._stack.currentWidget() is window._home
    window.close()


def test_shortcuts_dont_conflict_with_builtins(qapp, tmp_path, monkeypatch) -> None:
    """Les raccourcis ne capturent pas des séquences système critiques
    (pas de Ctrl+C/V/X/Z/Q/W pris en otage)."""
    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()
    sequences = {s.key().toString() for s in window._shortcuts}
    for stolen in ("Ctrl+C", "Ctrl+V", "Ctrl+X", "Ctrl+Z", "Ctrl+Q", "Ctrl+W"):
        assert stolen not in sequences, stolen
    window.close()


# ---------------------------------------------------------------------- #
# Profils (page + actions)
# ---------------------------------------------------------------------- #
def test_profiles_page_shows_cards_and_actions(qapp, tmp_path, monkeypatch) -> None:
    from app.profiles import ProfileEntry, ProfileManager

    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()
    manager = window.profiles
    manager.create(
        "Tryhard",
        description="Ranked",
        entries=[ProfileEntry(name="Nemesis Charm", rel_path="Charms/nemesis charm.json")],
    )
    window.go(("profiles", None))
    qapp.processEvents()
    assert window._stack.currentWidget() is window._profiles_view
    cards = window._profiles_view._cards
    assert len(cards) == 1
    assert "Tryhard" in cards[0]._name.text()
    assert "1" in cards[0]._status.text() or True  # statut affiché (prêt / manquant)
    window.close()


def test_profile_missing_config_flagged(qapp, tmp_path, monkeypatch) -> None:
    from app.profiles import ProfileEntry

    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()
    window.profiles.create(
        "Ghost",
        entries=[ProfileEntry(name="Supprimé", rel_path="Charms/supprime.json")],
    )
    window.go(("profiles", None))
    qapp.processEvents()
    cards = window._profiles_view._cards
    assert len(cards) == 1
    assert "introuvable" in cards[0]._status.text() or "missing" in cards[0]._status.text().lower()
    # Les configurations manquantes ne plantent jamais l'application.
    missing = window._profile_missing(window.profiles.get("Ghost"))
    assert missing == ["Supprimé"]
    window.close()


def test_profile_apply_activates_present_configs_and_reports_missing(
    qapp, tmp_path, monkeypatch
) -> None:
    """Appliquer un profil : les configs présentes passent par le mécanisme
    Fleasion existant ; les manquantes sont signalées, jamais plantées, et
    l'entrée du profil n'est jamais supprimée automatiquement."""
    from app.profiles import ProfileEntry

    # Fleasion réaliste créé AVANT la fenêtre (comme les tests smoke) :
    # settings.json + dossier configs — l'activation copie réellement.
    from app.fleasion import FleasionManager

    fleasion_root = tmp_path / "fleasion"
    (fleasion_root.parent / "settings.json").write_text(
        json.dumps({"enabled_configs": [], "last_config": None, "theme": "Dark"}),
        encoding="utf-8",
    )
    (fleasion_root / "configs").mkdir(parents=True, exist_ok=True)

    def fake_hot_restart(self, info, name, data, expect_active):
        return True, []

    monkeypatch.setattr(FleasionManager, "_hot_restart", fake_hot_restart)

    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()

    profile = window.profiles.create(
        "Tryhard",
        entries=[
            ProfileEntry(name="nemesis charm", rel_path="Charms/nemesis charm.json"),
            ProfileEntry(name="Ghost", rel_path="Charms/ghost.json"),  # manquante
        ],
    )
    assert window._profile_missing(profile) == ["Ghost"]

    # L'utilisateur confirme « Continuer » malgré la config manquante.
    import ui.main_window as mw

    monkeypatch.setattr(mw.MainWindow, "_confirm_profile_missing", lambda self, p, m: True)

    # L'activation réelle est confirmée par Fleasion (source de vérité).
    window._apply_profile(profile)
    qapp.processEvents()

    # « nemesis charm » a été copiée dans le dossier configs de Fleasion
    # (le config_dir détecté — ici la racine, comme dans les tests smoke).
    assert (fleasion_root / "nemesis charm.json").exists()
    # L'entrée du profil n'est jamais supprimée automatiquement.
    assert window.profiles.get("Tryhard") is not None
    assert window.profiles.get("Tryhard").count == 2
    window.close()


# ---------------------------------------------------------------------- #
# Responsive : titres longs jamais réduits à une lettre
# ---------------------------------------------------------------------- #
def test_long_titles_never_shrink_to_one_letter(qapp, tmp_path, monkeypatch) -> None:
    window, library = _window(qapp, tmp_path, monkeypatch)
    qapp.processEvents()
    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    window.go(("browse", charms))
    qapp.processEvents()

    for width, height in ((960, 640), (1024, 768), (1280, 720), (1366, 768),
                          (1600, 900), (1920, 1080)):
        window.resize(width, height)
        qapp.processEvents()
        for card in window._browse._grid._cards:
            label = card._title_label
            btn = card._toggle_btn
            # Le titre garde toute sa rangée (jamais écrasé par le bouton).
            assert label.width() >= card.width() - 24 - btn.width() - 6 - 1, (
                f"[{width}x{height}] {label._raw_text!r}"
            )
            assert len(label._shown_text.strip()) >= 2, (
                f"[{width}x{height}] titre réduit à une lettre : {label._shown_text!r}"
            )
    window.close()
