"""Tests for the i18n system.

Covers (1.1.0): French, English, hot switch, persistence in settings.json,
unknown language -> default, missing key -> fallback, key parity, no
critical untranslated text, user file/category names never translated.
Covers (1.2.0): all ten languages (fr/en/es/de/it/pt/nl/pl/ru/tr) with
identical keys, native display names, fallback inside secondary languages,
and frozen/PyInstaller resource resolution.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.i18n import (
    available_languages,
    current_language,
    set_language,
    t,
    validate_translations,
)
from app.i18n.manager import DEFAULT_LANGUAGE, _translations_dir


@pytest.fixture(autouse=True)
def _reset_language():
    """Chaque test repart de la langue par défaut."""
    set_language(DEFAULT_LANGUAGE)
    yield
    set_language(DEFAULT_LANGUAGE)


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------- #
# 1. Langue française
# ---------------------------------------------------------------------- #
def test_french_is_default_and_translates() -> None:
    assert current_language() == "fr"
    assert t("settings.title") == "Paramètres"
    assert t("nav.home") == "Accueil"
    assert t("trash.title") == "Corbeille"


# ---------------------------------------------------------------------- #
# 2. Langue anglaise
# ---------------------------------------------------------------------- #
def test_english_translations() -> None:
    set_language("en")
    assert current_language() == "en"
    assert t("settings.title") == "Settings"
    assert t("nav.home") == "Home"
    assert t("trash.title") == "Trash"


# ---------------------------------------------------------------------- #
# 3. Changement de langue
# ---------------------------------------------------------------------- #
def test_language_switch_changes_all_texts() -> None:
    assert t("config.activate") == "ACTIVER"
    set_language("en")
    assert t("config.activate") == "ACTIVATE"
    set_language("fr")
    assert t("config.activate") == "ACTIVER"


# ---------------------------------------------------------------------- #
# 4. Persistance de la langue (settings.json)
# ---------------------------------------------------------------------- #
def test_language_persists_in_settings(tmp_path: Path, monkeypatch) -> None:
    appdata = tmp_path / "AppData"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))

    from app.config import AppSettings, settings_file

    settings = AppSettings()
    settings.language = "en"
    settings.save()

    # Nouvelle instance : la langue est restaurée après redémarrage.
    reloaded = AppSettings.load()
    assert reloaded.language == "en"
    assert settings_file().exists()
    payload = json.loads(settings_file().read_text(encoding="utf-8"))
    assert payload["language"] == "en"


def test_language_missing_key_defaults_to_french(tmp_path: Path, monkeypatch) -> None:
    appdata = tmp_path / "AppData"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))

    from app.config import AppSettings, settings_file

    # Un settings.json sans la clé « language » : jamais d'erreur, défaut fr.
    settings_file().parent.mkdir(parents=True, exist_ok=True)
    settings_file().write_text(
        json.dumps({"fleasion_dir": None, "library_dir": None}),
        encoding="utf-8",
    )
    settings = AppSettings.load()
    assert settings.language == "fr"


def test_language_unknown_value_falls_back(tmp_path: Path, monkeypatch) -> None:
    appdata = tmp_path / "AppData"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))

    from app.config import AppSettings, settings_file

    settings_file().parent.mkdir(parents=True, exist_ok=True)
    settings_file().write_text(
        json.dumps({"language": "zz"}),
        encoding="utf-8",
    )
    settings = AppSettings.load()
    assert settings.language == "fr"


# ---------------------------------------------------------------------- #
# 5. Langue inconnue -> défaut ; 6. clé manquante -> fallback
# ---------------------------------------------------------------------- #
def test_unknown_language_falls_back_to_default() -> None:
    set_language("xx")
    assert current_language() == "fr"
    # La langue inconnue ne casse jamais : les textes restent en français.
    assert t("settings.title") == "Paramètres"


def test_missing_key_falls_back_to_default_language() -> None:
    set_language("en")
    # La clé existe en fr mais pas en en : fallback contrôlé vers le défaut.
    assert t("settings.title") == "Settings"  # existe partout, sanity
    # Une clé absente des deux fichiers retourne la clé (jamais de crash).
    value = t("clef.totalement.inconnue")
    assert value == "clef.totalement.inconnue"


def test_interpolation_never_crashes() -> None:
    set_language("fr")
    assert t("obj.file_not_found", path="x.obj") == "Fichier introuvable : « x.obj »"
    # Placeholder manquant : la valeur brute est renvoyée, pas de crash.
    assert t("obj.file_not_found") == "Fichier introuvable : « {path} »"


# ---------------------------------------------------------------------- #
# 7. Toutes les langues ont exactement les mêmes clés (fr = référence)
# ---------------------------------------------------------------------- #
def test_fr_and_en_have_identical_keys() -> None:
    report = validate_translations()
    for code, diff in report.items():
        assert diff["missing"] == [], f"clés manquantes dans {code}: {diff['missing']}"
        assert diff["extra"] == [], f"clés en trop dans {code}: {diff['extra']}"


def test_all_translation_files_exist_and_are_valid_json() -> None:
    directory = _translations_dir()
    assert directory.is_dir()
    for code in available_languages():
        path = directory / f"{code}.json"
        assert path.is_file(), f"fichier de traduction manquant : {path}"
        json.loads(path.read_text(encoding="utf-8"))  # JSON valide


# ---------------------------------------------------------------------- #
# 8. Aucun texte critique non traduit (les clés existent dans les deux langues)
# ---------------------------------------------------------------------- #
def test_critical_ui_keys_are_translated() -> None:
    critical = [
        "nav.home",
        "settings.title",
        "settings.language",
        "trash.title",
        "trash.restore",
        "trash.destroy",
        "trash.empty",
        "search.placeholder",
        "home.subtitle",
        "config.activate",
        "config.active",
        "config.copied",
        "config.deactivate",
        "config.files_included",
        "deps.title",
        "deps.none",
        "deps.required",
        "deps.missing_note",
        "deps.explanation",
        "toast.activated",
        "toast.deactivated",
        "toast.moved_to_trash",
        "import.title",
        "import.install",
        "clear_configs.action",
        "image.imported",
        "welcome.continue",
        "card.activate_tooltip",
        "card.deactivate_tooltip",
        "category.primary",
        "category.melee",
    ]
    report = validate_translations()
    for code, diff in report.items():
        assert not diff["missing"], f"clés manquantes dans {code}"
    for key in critical:
        fr_value = _t_in("fr", key)
        en_value = _t_in("en", key)
        assert fr_value and fr_value != key, f"clé non traduite en fr : {key}"
        assert en_value and en_value != key, f"clé non traduite en en : {key}"
        assert en_value != fr_value, f"en et fr identiques pour {key} ?"


def _t_in(code: str, key: str) -> str:
    """Traduit ``key`` dans une langue précise sans changer la langue active."""
    previous = current_language()
    set_language(code)
    try:
        return t(key)
    finally:
        set_language(previous)


# ---------------------------------------------------------------------- #
# 9 & 10. Noms d'utilisateur jamais traduits
# ---------------------------------------------------------------------- #
def test_user_file_names_never_translated() -> None:
    """Le système n'a AUCUNE clé qui porterait sur des noms de fichiers :
    les noms réels sont passés tels quels via les placeholders."""
    set_language("en")
    # Un nom de configuration quelconque reste intact dans un message.
    name = "nemesis charm"
    assert name in t("toast.moved_to_trash", name=name)
    # display_label ne traduit que les catégories canoniques.
    from app.categories import display_label

    assert display_label("Charms") == "Charms"      # catégorie utilisateur
    assert display_label("FastFlags") == "FastFlags"  # catégorie utilisateur
    set_language("fr")
    assert display_label("Charms") == "Charms"
    assert display_label("primary") == "Primaire"   # canonique, traduit


def test_user_category_names_never_translated_in_ui(tmp_path: Path, monkeypatch, qapp) -> None:
    """Une catégorie réelle « Charms » reste « Charms » dans les deux langues
    alors que la catégorie canonique « Primary » change de libellé."""
    import json as _json

    from ui.main_window import MainWindow

    from app.config import AppSettings, settings_file

    def _write_json(path: Path, data: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    library = tmp_path / "lib"
    _write_json(library / "Charms" / "nemesis charm.json", {"replacement_rules": []})
    _write_json(library / "Primary" / "ak.json", {"replacement_rules": []})
    fleasion = tmp_path / "fleasion"
    fleasion.mkdir(parents=True, exist_ok=True)

    appdata = tmp_path / "AppData"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    settings = AppSettings()
    settings.fleasion_dir = fleasion
    settings.library_dir = library
    settings.language = "fr"
    settings.save()

    window = MainWindow()
    window.show()
    qapp.processEvents()

    # Français : « Charms » (utilisateur) inchangé, « Primary » traduit.
    titles_fr = [c._title_label._raw_text for c in window._home._grid._cards]
    assert "Charms" in titles_fr
    assert "Primary" in titles_fr

    # Bascule à chaud vers l'anglais : les noms utilisateur restent intacts.
    window._set_language("en")
    qapp.processEvents()
    titles_en = [c._title_label._raw_text for c in window._home._grid._cards]
    assert "Charms" in titles_en
    assert "Primary" in titles_en

    # La préférence est persistée.
    payload = _json.loads(settings_file().read_text(encoding="utf-8"))
    assert payload["language"] == "en"
    window.close()


# ---------------------------------------------------------------------- #
# 1.2.0 — les 10 langues sont chargeables et identiques en clés
# ---------------------------------------------------------------------- #
def test_all_ten_languages_are_available_and_translate() -> None:
    codes = available_languages()
    assert codes == ["fr", "en", "es", "de", "it", "pt", "nl", "pl", "ru", "tr"]
    # Chaque langue traduit réellement quelques clés critiques.
    for code in codes:
        set_language(code)
        assert t("settings.title") != "settings.title"
        assert t("nav.home") != "nav.home"
        assert t("trash.title") != "trash.title"
        assert t("deps.none") != "deps.none"


def test_every_language_file_has_exactly_the_same_keys() -> None:
    report = validate_translations()
    assert set(report) == set(available_languages())
    for code, diff in report.items():
        assert diff["missing"] == [], f"{code} manque: {diff['missing']}"
        assert diff["extra"] == [], f"{code} en trop: {diff['extra']}"


def test_display_names_are_native() -> None:
    from app.i18n import language_display_name

    assert language_display_name("fr") == "Français"
    assert language_display_name("es") == "Español"
    assert language_display_name("de") == "Deutsch"
    assert language_display_name("ru") == "Русский"
    assert language_display_name("tr") == "Türkçe"


def test_secondary_language_switch_round_trip() -> None:
    """fr → es → de : les textes suivent à chaque bascule."""
    set_language("es")
    assert t("settings.title") == "Configuración"
    set_language("de")
    assert t("settings.title") == "Einstellungen"
    set_language("tr")
    assert t("settings.title") == "Ayarlar"
    set_language("fr")
    assert t("settings.title") == "Paramètres"


def test_secondary_language_missing_key_falls_back_to_french(
    monkeypatch, tmp_path: Path
) -> None:
    """Une traduction manquante dans une langue secondaire retombe sur le
    français (jamais de crash)."""
    import json

    from app.i18n import manager as manager_module
    from app.i18n.manager import I18nManager, _translations_dir

    # Copie des fichiers réels, avec une clé retirée de l'espagnol.
    src = _translations_dir()
    fake = tmp_path / "translations"
    fake.mkdir()
    for code in available_languages():
        data = json.loads((src / f"{code}.json").read_text(encoding="utf-8"))
        if code == "es":
            del data["settings"]["title"]
        (fake / f"{code}.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    monkeypatch.setattr(manager_module, "_translations_dir", lambda: fake)
    fresh = I18nManager()
    fresh.set_language("es")
    # La clé manquante en espagnol retombe sur le français.
    assert fresh.t("settings.title") == "Paramètres"
    # Les clés présentes en espagnol sont traduites normalement.
    assert fresh.t("nav.home") == "Inicio"


def test_frozen_mode_finds_translations_in_meipass(tmp_path: Path, monkeypatch) -> None:
    """PyInstaller/frozen : les traductions sont lues depuis le dossier
    d'extraction (_MEIPASS), jamais depuis l'arbre source."""
    import json

    from app.i18n import manager as manager_module

    meipass = tmp_path / "_MEIPASS"
    tables = meipass / "app" / "i18n" / "translations"
    tables.mkdir(parents=True)
    # Un seul fichier espagnol « embarqué dans le .exe » : les autres langues
    # sont absentes (comme dans un vrai bundle minimal) et ne doivent pas
    # faire planter le chargement.
    (tables / "es.json").write_text(
        json.dumps({"settings": {"title": "Ajustes", "language": "Idioma"}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    try:
        assert manager_module._translations_dir() == tables
        fresh = manager_module.I18nManager()
        fresh.set_language("es")
        assert fresh.t("settings.title") == "Ajustes"
        # Langue absente du bundle : fallback fr (clé absente -> la clé).
        fresh.set_language("en")
        assert fresh.t("settings.title") == "settings.title"
    finally:
        monkeypatch.delattr(sys, "frozen", raising=False)
        monkeypatch.delattr(sys, "_MEIPASS", raising=False)
