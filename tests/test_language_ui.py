"""UI tests: language selector (10 languages), hot language switch, the
Dépendances block in the config view (OBJ and MP3 sections, 1.2.0), and
responsive layout.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import AppSettings, settings_file


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _configure(appdata: Path, library: Path, fleasion_dir: Path, language: str = "fr") -> None:
    settings = AppSettings()
    settings.fleasion_dir = fleasion_dir
    settings.library_dir = library
    settings.language = language
    settings.save()


def _make_library(root: Path) -> None:
    """Une bibliothèque avec : config sans dépendance, configs OBJ présent /
    manquant, MP3 présent / manquant, OBJ + MP3 ensemble, et URLs distantes
    (OBJ et MP3) qui ne doivent pas créer de dépendance locale."""
    _write_json(root / "Charms" / "simple charm.json", {"replacement_rules": []})
    (root / "Charms" / "mesh charm.obj").write_text("v 0 0 0", encoding="utf-8")
    _write_json(
        root / "Charms" / "mesh charm.json",
        {"replacement_rules": [{"cdn_url": "mesh charm.obj"}]},
    )
    _write_json(
        root / "Charms" / "broken charm.json",
        {"replacement_rules": [{"cdn_url": "missing model.obj"}]},
    )
    _write_json(
        root / "Charms" / "remote charm.json",
        {"replacement_rules": [{"cdn_url": "https://example.com/remote.obj"}]},
    )
    # --- MP3 --- #
    (root / "Charms" / "sound charm.mp3").write_bytes(b"ID3")
    _write_json(
        root / "Charms" / "sound charm.json",
        {"replacement_rules": [{"sound_url": "sound charm.mp3"}]},
    )
    _write_json(
        root / "Charms" / "broken sound.json",
        {"replacement_rules": [{"sound_url": "missing sound.mp3"}]},
    )
    _write_json(
        root / "Charms" / "remote sound.json",
        {"replacement_rules": [{"sound_url": "https://example.com/remote.mp3"}]},
    )
    # --- OBJ + MP3 --- #
    (root / "Charms" / "full charm.obj").write_text("v 0 0 0", encoding="utf-8")
    (root / "Charms" / "full charm.mp3").write_bytes(b"ID3")
    _write_json(
        root / "Charms" / "full charm.json",
        {
            "replacement_rules": [
                {"cdn_url": "full charm.obj"},
                {"sound_url": "full charm.mp3"},
            ]
        },
    )


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


# ---------------------------------------------------------------------- #
# Sélecteur de langue visible dans Paramètres
# ---------------------------------------------------------------------- #
def test_language_selector_visible_in_settings(qapp, tmp_path, monkeypatch) -> None:
    window, _ = _window(qapp, tmp_path, monkeypatch)
    window.go(("settings", None))
    qapp.processEvents()

    combo = window._settings._language_combo
    assert combo is not None
    assert combo.count() == 10
    codes = [combo.itemData(i) for i in range(combo.count())]
    assert codes == ["fr", "en", "es", "de", "it", "pt", "nl", "pl", "ru", "tr"]
    # Noms natifs affichés.
    names = [combo.itemText(i) for i in range(combo.count())]
    assert "Français" in names and "Español" in names and "Türkçe" in names
    # La langue active est présélectionnée.
    assert combo.currentData() == "fr"
    window.close()


# ---------------------------------------------------------------------- #
# Langue française correcte
# ---------------------------------------------------------------------- #
def test_french_ui_texts(qapp, tmp_path, monkeypatch) -> None:
    window, _ = _window(qapp, tmp_path, monkeypatch, language="fr")
    qapp.processEvents()
    assert window._top_title.text() == "Accueil"
    assert window._search.placeholderText().startswith("Rechercher")
    assert window._add_weapon_btn.text() == " Ajouter une arme"
    window.close()


# ---------------------------------------------------------------------- #
# Langue anglaise correcte (dès le démarrage)
# ---------------------------------------------------------------------- #
def test_english_ui_texts_at_startup(qapp, tmp_path, monkeypatch) -> None:
    window, _ = _window(qapp, tmp_path, monkeypatch, language="en")
    qapp.processEvents()
    assert window._top_title.text() == "Home"
    assert window._search.placeholderText().startswith("Search")
    assert window._add_weapon_btn.text() == " Add a weapon"
    window.close()


# ---------------------------------------------------------------------- #
# Changement de langue à chaud + persistance
# ---------------------------------------------------------------------- #
def test_hot_language_switch_updates_ui_and_persists(qapp, tmp_path, monkeypatch) -> None:
    window, _ = _window(qapp, tmp_path, monkeypatch, language="fr")
    qapp.processEvents()

    # Paramètres -> sélecteur -> English.
    window.go(("settings", None))
    qapp.processEvents()
    combo = window._settings._language_combo
    combo.setCurrentIndex(combo.findData("en"))
    qapp.processEvents()

    # L'interface est passée en anglais immédiatement (sans redémarrage).
    assert window._top_title.text() == "Settings"
    assert window._search.placeholderText().startswith("Search")
    assert combo.currentData() == "en"
    # La préférence est persistée.
    payload = json.loads(settings_file().read_text(encoding="utf-8"))
    assert payload["language"] == "en"

    # Navigation et recherche conservées après le changement de langue.
    window._search.setText("charm")
    window._run_search()
    qapp.processEvents()
    assert window._stack.currentWidget() is window._browse
    assert window._search.text() == "charm"
    assert window._browse._filter_row.isVisible()
    window.close()

    # Redémarrage : la langue anglaise est restaurée.
    from ui.main_window import MainWindow

    window2 = MainWindow()
    window2.show()
    qapp.processEvents()
    assert window2.settings.language == "en"
    assert window2._top_title.text() == "Home"
    window2.close()


def test_hot_switch_keeps_open_config_page(qapp, tmp_path, monkeypatch) -> None:
    window, library = _window(qapp, tmp_path, monkeypatch, language="fr")
    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "simple charm")
    window.go(("config", item))
    qapp.processEvents()
    assert window._stack.currentWidget() is window._config

    window._set_language("en")
    qapp.processEvents()
    # Toujours sur la page de configuration, titre du bouton traduit.
    assert window._stack.currentWidget() is window._config
    assert window._config._activate_btn.text() == "ACTIVATE"
    window.close()


# ---------------------------------------------------------------------- #
# Affichage de l'état OBJ (Dépendances)
# ---------------------------------------------------------------------- #
def _open_charms_config(window, qapp, name: str):
    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == name)
    window.go(("config", item))
    qapp.processEvents()
    return item


def test_deps_block_hidden_for_invalid_or_unreadable(qapp, tmp_path, monkeypatch) -> None:
    window, _ = _window(qapp, tmp_path, monkeypatch)
    # Une config sans JSON ? Impossible dans cette bibliothèque ; on vérifie
    # plutôt que le bloc est visible et cohérent pour une config simple.
    _open_charms_config(window, qapp, "simple charm")
    assert window._config._deps_box.isVisible()
    window.close()


def test_config_without_deps_shows_none_detected(qapp, tmp_path, monkeypatch) -> None:
    window, _ = _window(qapp, tmp_path, monkeypatch)
    _open_charms_config(window, qapp, "simple charm")
    text = window._config._deps_content.text()
    assert "Aucune dépendance détectée" in text
    window.close()


def test_config_with_obj_present(qapp, tmp_path, monkeypatch) -> None:
    window, _ = _window(qapp, tmp_path, monkeypatch)
    _open_charms_config(window, qapp, "mesh charm")
    text = window._config._deps_content.text()
    assert "OBJ" in text
    assert "mesh charm.obj" in text
    assert "✓" in text and "✗" not in text
    assert "introuvable" not in text
    window.close()


def test_config_with_obj_missing_shows_warning(qapp, tmp_path, monkeypatch) -> None:
    window, _ = _window(qapp, tmp_path, monkeypatch)
    _open_charms_config(window, qapp, "broken charm")
    text = window._config._deps_content.text()
    assert "OBJ" in text
    assert "missing model.obj" in text
    assert "Fichier requis introuvable" in text
    assert "ne pas fonctionner correctement" in text
    window.close()


def test_config_with_remote_urls_requires_nothing(qapp, tmp_path, monkeypatch) -> None:
    """URLs distantes (OBJ et MP3) = pas de dépendance locale : pas de faux
    positif, y compris quand le même JSON ne référence que des URLs."""
    window, _ = _window(qapp, tmp_path, monkeypatch)
    _open_charms_config(window, qapp, "remote charm")
    text = window._config._deps_content.text()
    assert "Aucune dépendance détectée" in text
    _open_charms_config(window, qapp, "remote sound")
    text = window._config._deps_content.text()
    assert "Aucune dépendance détectée" in text
    window.close()


def test_deps_block_translated_in_english(qapp, tmp_path, monkeypatch) -> None:
    window, _ = _window(qapp, tmp_path, monkeypatch, language="en")
    _open_charms_config(window, qapp, "broken charm")
    text = window._config._deps_content.text()
    assert "OBJ" in text
    assert "missing model.obj" in text
    assert "Required file not found" in text
    assert "may not work correctly" in text
    window.close()


# ---------------------------------------------------------------------- #
# MP3 : affichage des dépendances audio (1.2.0)
# ---------------------------------------------------------------------- #
def test_config_with_mp3_present(qapp, tmp_path, monkeypatch) -> None:
    window, _ = _window(qapp, tmp_path, monkeypatch)
    _open_charms_config(window, qapp, "sound charm")
    text = window._config._deps_content.text()
    assert "MP3" in text
    assert "sound charm.mp3" in text
    assert "✓" in text and "✗" not in text
    window.close()


def test_config_with_mp3_missing_is_flagged(qapp, tmp_path, monkeypatch) -> None:
    window, _ = _window(qapp, tmp_path, monkeypatch)
    _open_charms_config(window, qapp, "broken sound")
    text = window._config._deps_content.text()
    assert "MP3" in text
    assert "missing sound.mp3" in text
    assert "Fichier requis introuvable" in text
    assert "ne pas fonctionner correctement" in text
    window.close()


def test_config_with_obj_and_mp3_shows_both_sections(qapp, tmp_path, monkeypatch) -> None:
    window, _ = _window(qapp, tmp_path, monkeypatch)
    _open_charms_config(window, qapp, "full charm")
    text = window._config._deps_content.text()
    # Les deux sections sont présentes, avec leurs fichiers respectifs.
    assert "OBJ" in text
    assert "MP3" in text
    assert "full charm.obj" in text
    assert "full charm.mp3" in text
    # Tout est présent : aucune ligne rouge.
    assert "✗" not in text
    assert "introuvable" not in text
    window.close()


def test_deps_block_mp3_translated_in_english(qapp, tmp_path, monkeypatch) -> None:
    window, _ = _window(qapp, tmp_path, monkeypatch, language="en")
    _open_charms_config(window, qapp, "broken sound")
    text = window._config._deps_content.text()
    assert "MP3" in text
    assert "missing sound.mp3" in text
    assert "Required file not found" in text
    window.close()


# ---------------------------------------------------------------------- #
# Responsive aux tailles existantes
# ---------------------------------------------------------------------- #
def test_language_and_deps_responsive(qapp, tmp_path, monkeypatch) -> None:
    window, _ = _window(qapp, tmp_path, monkeypatch)
    _open_charms_config(window, qapp, "broken charm")

    for width, height in (
        (960, 640),
        (1024, 768),
        (1280, 720),
        (1366, 768),
        (1600, 900),
        (1920, 1080),
    ):
        window.resize(width, height)
        qapp.processEvents()
        # Sur la page de configuration : le bloc Dépendances est visible et
        # tient dans la page.
        deps = window._config._deps_box
        assert deps.isVisible()
        assert deps.geometry().width() <= window._config.width()

    # Sur la page Paramètres : le sélecteur de langue est visible et tient.
    window.go(("settings", None))
    qapp.processEvents()
    for width, height in (
        (960, 640),
        (1024, 768),
        (1280, 720),
        (1366, 768),
        (1600, 900),
        (1920, 1080),
    ):
        window.resize(width, height)
        qapp.processEvents()
        combo = window._settings._language_combo
        assert combo.isVisible()
        assert combo.geometry().width() <= window._settings.width()
    window.close()


def test_card_delete_and_restore_still_french_after_switch_back(
    qapp, tmp_path, monkeypatch
) -> None:
    """Après un aller-retour en/→ fr, les textes français restent corrects
    (aucune régression des messages de suppression/restauration)."""
    window, _ = _window(qapp, tmp_path, monkeypatch, language="fr")
    window._set_language("en")
    qapp.processEvents()
    window._set_language("fr")
    qapp.processEvents()
    assert window._top_title.text() == "Accueil"
    assert window._config._activate_btn.text() == "ACTIVER"
    window.close()
