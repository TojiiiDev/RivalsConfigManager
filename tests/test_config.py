"""Tests for app/config.py — settings persistence (no hard-coded paths)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app import config as config_module
from app.config import AppSettings


@pytest.fixture
def fake_appdata(tmp_path: Path, monkeypatch) -> Path:
    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    return appdata


def test_defaults_are_empty(fake_appdata: Path) -> None:
    settings = AppSettings.load()
    assert settings.fleasion_dir is None
    assert settings.library_dir is None
    assert not settings.is_configured


def test_save_and_load_roundtrip(fake_appdata: Path) -> None:
    settings = AppSettings()
    settings.fleasion_dir = Path("C:/Users/other/AppData/Local/FleasionNT/config")
    settings.library_dir = Path("D:/Mes Configs Rivals")
    settings.save()

    loaded = AppSettings.load()
    assert loaded.fleasion_dir == Path("C:/Users/other/AppData/Local/FleasionNT/config")
    assert loaded.library_dir == Path("D:/Mes Configs Rivals")
    assert loaded.is_configured


def test_backup_flag_roundtrip(fake_appdata: Path) -> None:
    settings = AppSettings()
    settings.fleasion_dir = Path("C:/x")
    settings.library_dir = Path("C:/y")
    settings.backup_before_overwrite = False
    settings.save()

    loaded = AppSettings.load()
    assert loaded.backup_before_overwrite is False


def test_hot_activation_defaults_to_true(fake_appdata: Path) -> None:
    """Clé absente → valeur par défaut ``true`` (les utilisateurs actuels
    conservent le comportement d'activation à chaud après mise à jour)."""
    settings = AppSettings.load()
    assert settings.hot_activation_enabled is True

    # Clé explicitement absente d'un fichier existant : toujours true.
    (config_module.settings_file()).write_text(
        '{"library_dir": "C:/x", "fleasion_dir": "C:/y"}', encoding="utf-8"
    )
    loaded = AppSettings.load()
    assert loaded.hot_activation_enabled is True


def test_hot_activation_false_roundtrip(fake_appdata: Path) -> None:
    settings = AppSettings()
    settings.fleasion_dir = Path("C:/x")
    settings.library_dir = Path("C:/y")
    settings.hot_activation_enabled = False
    settings.save()

    loaded = AppSettings.load()
    assert loaded.hot_activation_enabled is False

    # La clé est bien écrite dans le fichier JSON.
    import json

    payload = json.loads(config_module.settings_file().read_text(encoding="utf-8"))
    assert payload["hot_activation_enabled"] is False


def test_hot_activation_restored_after_restart(fake_appdata: Path) -> None:
    """Le réglage survit à un redémarrage de l'application (deux chargements
    successifs à partir du même fichier)."""
    settings = AppSettings()
    settings.fleasion_dir = Path("C:/x")
    settings.library_dir = Path("C:/y")
    settings.hot_activation_enabled = True
    settings.save()
    assert AppSettings.load().hot_activation_enabled is True

    settings.hot_activation_enabled = False
    settings.save()
    assert AppSettings.load().hot_activation_enabled is False
    assert AppSettings.load().hot_activation_enabled is False  # restart


def test_corrupt_settings_falls_back(fake_appdata: Path) -> None:
    target = config_module.settings_file()
    target.write_text("{not json", encoding="utf-8")
    settings = AppSettings.load()
    assert settings.fleasion_dir is None
    assert settings.library_dir is None


def test_settings_in_appdata_not_cwd(fake_appdata: Path, tmp_path: Path, monkeypatch) -> None:
    """Settings must be stored per-user, never next to the program."""
    settings = AppSettings()
    settings.fleasion_dir = Path("C:/x")
    settings.library_dir = Path("C:/y")
    settings.save()

    assert config_module.settings_file().is_relative_to(fake_appdata)
    # Nothing written to the working directory.
    assert not (tmp_path / "settings.json").exists()


def test_backups_dir_created(fake_appdata: Path) -> None:
    backups = config_module.backups_dir()
    assert backups.is_dir()
    assert backups.name == "backups"
    assert backups.is_relative_to(fake_appdata)
