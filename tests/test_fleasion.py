"""Tests for app/fleasion.py — detection, activation, selection, backup."""

from __future__ import annotations

import json
from pathlib import Path

from app.backup_manager import BackupManager
from app.file_manager import FileManager
from app.fleasion import FleasionManager, config_name
from app.models import KIND_FILE, KIND_FOLDER, ConfigItem
from app.trash import Trash


def _fleasion_root(tmp_path: Path, enabled: list[str] | None = None) -> Path:
    """A realistic FleasionNT layout: settings.json + configs/."""
    enabled = enabled if enabled is not None else ["Crosskey"]
    root = tmp_path / "AppData" / "Local" / "FleasionNT"
    root.mkdir(parents=True)
    (root / "configs").mkdir()
    _write_settings(
        root / "settings.json",
        {
            "enabled_configs": enabled,
            "last_config": enabled[0] if enabled else None,
            "theme": "Dark",
        },
    )
    return root


def _write_settings(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _read_settings(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _manager(root: Path) -> FleasionManager:
    return FleasionManager(root / "config", BackupManager(root / ".." / "backups"))


def _item(tmp_path: Path, name: str = "nemesis charm") -> ConfigItem:
    folder = tmp_path / "Charms"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    path.write_text('{"replacement_rules": []}', encoding="utf-8")
    return ConfigItem(name=name, path=path, kind=KIND_FILE, files=[path], json_files=[path])


def test_config_name_file_and_folder(tmp_path: Path) -> None:
    item = _item(tmp_path, "ak-47")
    assert config_name(item) == "ak-47"
    folder = tmp_path / "pack"
    folder.mkdir()
    fc = ConfigItem(
        name="pack",
        path=folder,
        kind=KIND_FOLDER,
        files=[folder / "config.json"],
        json_files=[folder / "config.json"],
    )
    assert config_name(fc) == "config"


def test_detect_finds_settings_and_configs(tmp_path: Path) -> None:
    root = _fleasion_root(tmp_path)
    manager = FleasionManager(root / "config", BackupManager(tmp_path / "backups"))
    info = manager.detect()
    assert info.found
    assert info.root == root
    assert info.settings_path == root / "settings.json"
    assert info.config_dir == root / "configs"
    assert info.enabled_configs == ["Crosskey"]
    assert info.last_config == "Crosskey"


def test_detect_without_settings_falls_back(tmp_path: Path) -> None:
    configured = tmp_path / "config"
    configured.mkdir()
    manager = FleasionManager(configured, BackupManager(tmp_path / "backups"))
    info = manager.detect()
    assert not info.found
    assert info.config_dir == configured


def test_status_states(tmp_path: Path) -> None:
    root = _fleasion_root(tmp_path)
    (root / "configs" / "ak-47.json").write_text("{}", encoding="utf-8")
    manager = FleasionManager(root / "config", BackupManager(tmp_path / "backups"))

    assert manager.status(_item(tmp_path, "ghost")) == "inactive"
    assert manager.status(_item(tmp_path, "ak-47")) == "copied"
    assert manager.status(_item(tmp_path, "Crosskey")) == "active"


def test_activate_copies_and_selects(tmp_path: Path) -> None:
    root = _fleasion_root(tmp_path)
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")

    outcome = manager.activate(item, FileManager(BackupManager(tmp_path / "backups")))

    assert outcome.ok
    assert outcome.selected
    assert not outcome.needs_manual_selection
    assert "nemesis charm.json" in outcome.copied
    assert (root / "configs" / "nemesis charm.json").exists()

    settings = _read_settings(root / "settings.json")
    assert "nemesis charm" in settings["enabled_configs"]
    assert settings["last_config"] == "nemesis charm"
    # Only the necessary values changed: the rest is preserved.
    assert settings["theme"] == "Dark"


def test_activate_backs_up_settings_before_modification(tmp_path: Path) -> None:
    root = _fleasion_root(tmp_path)
    backups = tmp_path / "backups"
    manager = FleasionManager(root / "config", BackupManager(backups))
    item = _item(tmp_path / "lib", "nemesis charm")

    outcome = manager.activate(item, FileManager(BackupManager(backups)))
    assert outcome.ok and outcome.selected

    infos = BackupManager(backups).list_backups()
    assert infos, "aucune sauvegarde créée"
    backed = [p for info in infos for p in info.files if p.name == "settings.json"]
    assert backed, "settings.json non sauvegardé"
    # The backup holds the pre-modification content.
    assert _read_settings(backed[0])["enabled_configs"] == ["Crosskey"]


def test_activate_existing_selection_is_idempotent(tmp_path: Path) -> None:
    root = _fleasion_root(tmp_path)
    (root / "configs" / "Crosskey.json").write_text("{}", encoding="utf-8")
    manager = _manager(root)
    item = _item(tmp_path / "lib", "Crosskey")

    outcome = manager.activate(item, FileManager(BackupManager(tmp_path / "backups")))
    assert outcome.ok and outcome.selected
    settings = _read_settings(root / "settings.json")
    assert settings["enabled_configs"] == ["Crosskey"]  # no duplicate
    assert settings["last_config"] == "Crosskey"


def test_activate_without_settings_copy_only(tmp_path: Path) -> None:
    configured = tmp_path / "config"
    manager = FleasionManager(configured, BackupManager(tmp_path / "backups"))
    item = _item(tmp_path / "lib", "nemesis charm")

    outcome = manager.activate(item, FileManager(BackupManager(tmp_path / "backups")))
    assert outcome.ok
    assert not outcome.selected
    assert outcome.needs_manual_selection
    assert (configured / "nemesis charm.json").exists()
    assert not (configured / "settings.json").exists()


def test_activate_corrupt_settings_fails_cleanly(tmp_path: Path) -> None:
    root = tmp_path / "AppData" / "Local" / "FleasionNT"
    root.mkdir(parents=True)
    (root / "configs").mkdir()
    (root / "settings.json").write_text("{not valid json", encoding="utf-8")
    manager = FleasionManager(root / "config", BackupManager(tmp_path / "backups"))
    item = _item(tmp_path / "lib", "nemesis charm")

    outcome = manager.activate(item, FileManager(BackupManager(tmp_path / "backups")))
    assert outcome.ok  # files were still copied
    assert not outcome.selected
    assert outcome.needs_manual_selection
    assert any("settings.json" in e for e in outcome.errors)
    # settings.json was NOT modified.
    assert (root / "settings.json").read_text(encoding="utf-8") == "{not valid json"


def test_activate_inaccessible_destination(tmp_path: Path) -> None:
    """The configured Fleasion folder is a file (not a folder) -> clean error."""
    blocked = tmp_path / "config"
    blocked.write_text("blocked", encoding="utf-8")
    manager = FleasionManager(blocked, BackupManager(tmp_path / "backups"))
    item = _item(tmp_path / "lib", "nemesis charm")

    outcome = manager.activate(item, FileManager(BackupManager(tmp_path / "backups")))
    assert not outcome.ok
    assert outcome.errors


def test_activate_invalid_json_aborts_before_selection(tmp_path: Path) -> None:
    root = _fleasion_root(tmp_path)
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")
    item.json_files[0].write_text("{bad", encoding="utf-8")

    outcome = manager.activate(item, FileManager(BackupManager(tmp_path / "backups")))
    assert not outcome.ok
    assert not outcome.selected
    settings = _read_settings(root / "settings.json")
    assert "nemesis charm" not in settings["enabled_configs"]
    assert not (root / "configs" / "nemesis charm.json").exists()


# ---------------------------------------------------------------------- #
# Deactivation
# ---------------------------------------------------------------------- #

def test_deactivate_removes_selection_and_copies(tmp_path: Path) -> None:
    root = _fleasion_root(tmp_path, enabled=["nemesis charm"])
    (root / "configs" / "nemesis charm.json").write_text("{}", encoding="utf-8")
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")

    outcome = manager.deactivate(item, FileManager(BackupManager(tmp_path / "backups")))
    assert outcome.ok
    assert outcome.selection_cleared
    assert outcome.removed == ["nemesis charm.json"]
    assert not (root / "configs" / "nemesis charm.json").exists()
    settings = _read_settings(root / "settings.json")
    assert "nemesis charm" not in settings["enabled_configs"]
    # Only the necessary values changed.
    assert settings["theme"] == "Dark"
    # The library keeps the mod: reactivation stays possible.
    assert (tmp_path / "lib" / "Charms" / "nemesis charm.json").exists()


def test_deactivate_clears_last_config(tmp_path: Path) -> None:
    root = _fleasion_root(tmp_path, enabled=["nemesis charm", "Crosskey"])
    settings = _read_settings(root / "settings.json")
    settings["last_config"] = "nemesis charm"
    _write_settings(root / "settings.json", settings)
    (root / "configs" / "nemesis charm.json").write_text("{}", encoding="utf-8")
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")

    outcome = manager.deactivate(item, FileManager(BackupManager(tmp_path / "backups")))
    assert outcome.ok and outcome.selection_cleared
    settings = _read_settings(root / "settings.json")
    assert settings["enabled_configs"] == ["Crosskey"]
    assert settings["last_config"] == "Crosskey"


def test_deactivate_then_reactivate(tmp_path: Path) -> None:
    root = _fleasion_root(tmp_path, enabled=["nemesis charm"])
    (root / "configs" / "nemesis charm.json").write_text("{}", encoding="utf-8")
    backups = tmp_path / "backups"
    fm = FileManager(BackupManager(backups))
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")

    outcome = manager.deactivate(item, fm)
    assert outcome.ok and outcome.selection_cleared
    assert not (root / "configs" / "nemesis charm.json").exists()

    # Réactivation : les fichiers reviennent et la sélection est restaurée.
    again = manager.activate(item, fm)
    assert again.ok and again.selected
    assert (root / "configs" / "nemesis charm.json").exists()
    assert "nemesis charm" in _read_settings(root / "settings.json")["enabled_configs"]


def test_deactivate_when_inactive_is_noop(tmp_path: Path) -> None:
    root = _fleasion_root(tmp_path, enabled=[])
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")

    outcome = manager.deactivate(item, FileManager(BackupManager(tmp_path / "backups")))
    assert outcome.ok
    assert outcome.removed == []
    assert not outcome.selection_cleared


def test_deactivate_without_settings_removes_copies(tmp_path: Path) -> None:
    configured = tmp_path / "config"
    configured.mkdir()
    (configured / "nemesis charm.json").write_text("{}", encoding="utf-8")
    manager = FleasionManager(configured, BackupManager(tmp_path / "backups"))
    item = _item(tmp_path / "lib", "nemesis charm")

    outcome = manager.deactivate(item, FileManager(BackupManager(tmp_path / "backups")))
    assert outcome.ok
    assert outcome.removed == ["nemesis charm.json"]
    assert not (configured / "nemesis charm.json").exists()
    assert not outcome.selection_cleared


def test_deactivate_corrupt_settings_removes_copies_and_reports(tmp_path: Path) -> None:
    root = tmp_path / "AppData" / "Local" / "FleasionNT"
    root.mkdir(parents=True)
    (root / "configs").mkdir()
    (root / "settings.json").write_text("{bad", encoding="utf-8")
    (root / "configs" / "nemesis charm.json").write_text("{}", encoding="utf-8")
    manager = FleasionManager(root / "config", BackupManager(tmp_path / "backups"))
    item = _item(tmp_path / "lib", "nemesis charm")

    outcome = manager.deactivate(item, FileManager(BackupManager(tmp_path / "backups")))
    assert outcome.removed == ["nemesis charm.json"]
    assert outcome.errors  # selection could not be updated
    assert not outcome.ok
    # The corrupt file is left untouched.
    assert (root / "settings.json").read_text(encoding="utf-8") == "{bad"


def test_restore_settings_from_backup(tmp_path: Path) -> None:
    """The backed-up settings.json can be restored via BackupManager."""
    root = _fleasion_root(tmp_path)
    backups_dir = tmp_path / "backups"
    backup_manager = BackupManager(backups_dir)
    manager = FleasionManager(root / "config", backup_manager)
    item = _item(tmp_path / "lib", "nemesis charm")

    manager.activate(item, FileManager(backup_manager))
    assert "nemesis charm" in _read_settings(root / "settings.json")["enabled_configs"]

    # Restore the most recent backup -> the original selection comes back.
    infos = backup_manager.list_backups()
    backup = next(
        info for info in infos if any(p.name == "settings.json" for p in info.files)
    )
    errors = manager.restore_backup(backup)
    assert errors == []
    settings = _read_settings(root / "settings.json")
    assert settings["enabled_configs"] == ["Crosskey"]
    assert "nemesis charm" not in settings["enabled_configs"]


# ---------------------------------------------------------------------- #
# Source de vérité : état réel relu après activation / désactivation
# ---------------------------------------------------------------------- #

def test_status_reflects_real_fleasion_state_not_app_assumptions(tmp_path: Path) -> None:
    """État incohérent application/Fleasion : ``status()`` reflète TOUJOURS
    l'état réel de Fleasion (source de vérité), jamais ce que l'application
    suppose.

    - fichiers copiés par l'app mais désélectionnés manuellement dans
      Fleasion → « copied », jamais « active » ;
    - sélection présente dans settings.json même si le fichier a disparu
      → « active » (c'est Fleasion qui décide)."""
    root = _fleasion_root(tmp_path, enabled=[])
    (root / "configs" / "ak-47.json").write_text("{}", encoding="utf-8")
    manager = FleasionManager(root / "config", BackupManager(tmp_path / "backups"))
    # L'app a copié ak-47 (fichier présent) mais Fleasion ne l'a pas
    # sélectionné : l'état réel dit « copied », jamais « active ».
    assert manager.status(_item(tmp_path, "ak-47")) == "copied"

    root2 = _fleasion_root(tmp_path / "other", enabled=["Crosskey"])
    manager2 = FleasionManager(root2 / "config", BackupManager(tmp_path / "backups"))
    # Fleasion sélectionne Crosskey dans settings.json même si son fichier a
    # disparu du dossier actif : l'état réel prime.
    assert manager2.status(_item(tmp_path, "Crosskey")) == "active"


def test_activate_write_failure_no_false_success(tmp_path: Path, monkeypatch) -> None:
    """Échec d'écriture de settings.json pendant l'activation : jamais de
    faux succès — la config n'est pas marquée sélectionnée, l'erreur est
    rapportée et ``status()`` (état réel) ne dit pas « active »."""
    import app.fleasion as fleasion_mod

    root = _fleasion_root(tmp_path)
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")
    monkeypatch.setattr(fleasion_mod, "_write_settings", lambda p, d: False)

    outcome = manager.activate(item, FileManager(BackupManager(tmp_path / "backups")))
    assert outcome.ok  # les fichiers ont bien été copiés
    assert not outcome.selected
    assert outcome.needs_manual_selection
    assert any("settings.json" in e for e in outcome.errors)
    settings = _read_settings(root / "settings.json")
    assert "nemesis charm" not in settings["enabled_configs"]
    # La relecture de l'état réel ne confirme pas l'activation.
    assert manager.status(item) != "active"


def test_activate_missing_config_fails_cleanly(tmp_path: Path) -> None:
    """Configuration inexistante (fichier source absent) → échec propre,
    aucune écriture, aucun faux succès."""
    root = _fleasion_root(tmp_path)
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")
    item.path.unlink()  # la source disparaît avant l'activation

    outcome = manager.activate(item, FileManager(BackupManager(tmp_path / "backups")))
    assert not outcome.ok
    assert not outcome.selected
    assert any("Fichier manquant" in e for e in outcome.errors)
    assert not (root / "configs" / "nemesis charm.json").exists()
    settings = _read_settings(root / "settings.json")
    assert "nemesis charm" not in settings["enabled_configs"]


def test_activate_preserves_other_enabled_configs(tmp_path: Path) -> None:
    """Plusieurs configurations actives : activer une nouvelle config ajoute
    son nom SANS toucher aux autres, et ``status()`` reflète chaque état."""
    root = _fleasion_root(tmp_path, enabled=["Crosskey", "Keyper"])
    (root / "configs" / "Crosskey.json").write_text("{}", encoding="utf-8")
    (root / "configs" / "Keyper.json").write_text("{}", encoding="utf-8")
    manager = _manager(root)
    fm = FileManager(BackupManager(tmp_path / "backups"))
    item = _item(tmp_path / "lib", "nemesis charm")

    outcome = manager.activate(item, fm)
    assert outcome.ok and outcome.selected
    settings = _read_settings(root / "settings.json")
    assert settings["enabled_configs"] == ["Crosskey", "Keyper", "nemesis charm"]
    # Chaque configuration garde son propre état réel.
    assert manager.status(_item(tmp_path, "Crosskey")) == "active"
    assert manager.status(_item(tmp_path, "Keyper")) == "active"
    assert manager.status(_item(tmp_path, "nemesis charm")) == "active"

    # Désactiver la nouvelle n'affecte pas les autres.
    deact = manager.deactivate(item, fm)
    assert deact.ok
    settings = _read_settings(root / "settings.json")
    assert settings["enabled_configs"] == ["Crosskey", "Keyper"]


def test_deactivate_write_failure_keeps_fleasion_active(tmp_path: Path, monkeypatch) -> None:
    """Échec d'écriture pendant la désactivation : l'état réel de Fleasion
    dit encore « active » — jamais de faux succès de désactivation."""
    import app.fleasion as fleasion_mod

    root = _fleasion_root(tmp_path, enabled=["nemesis charm"])
    (root / "configs" / "nemesis charm.json").write_text("{}", encoding="utf-8")
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")
    monkeypatch.setattr(fleasion_mod, "_write_settings", lambda p, d: False)

    outcome = manager.deactivate(item, FileManager(BackupManager(tmp_path / "backups")))
    assert not outcome.ok
    assert not outcome.selection_cleared
    # L'état réel (settings.json relu) considère encore la config active.
    assert manager.status(item) == "active"
    settings = _read_settings(root / "settings.json")
    assert "nemesis charm" in settings["enabled_configs"]


def test_real_controlled_fleasion_instance_roundtrip(tmp_path: Path) -> None:
    """Test réel contrôlé sur une instance Fleasion temporaire (settings.json
    + configs/ complets) : activation vérifiée contre l'état réel, puis
    désactivation vérifiée, puis réactivation. Aucun fichier réel touché."""
    root = _fleasion_root(tmp_path, enabled=[])
    backups_dir = tmp_path / "backups"
    backup_manager = BackupManager(backups_dir)
    manager = FleasionManager(root / "config", backup_manager)
    fm = FileManager(backup_manager)
    item = _item(tmp_path / "lib", "nemesis charm")

    # --- Activation ---
    outcome = manager.activate(item, fm)
    assert outcome.ok and outcome.selected
    # Vérification post-action : l'état réel relu confirme l'activation.
    assert manager.status(item) == "active"
    settings = _read_settings(root / "settings.json")
    assert "nemesis charm" in settings["enabled_configs"]
    assert settings["last_config"] == "nemesis charm"
    assert (root / "configs" / "nemesis charm.json").exists()

    # --- Désactivation ---
    deact = manager.deactivate(item, fm)
    assert deact.ok and deact.selection_cleared
    # Vérification post-action : Fleasion ne considère plus la config active.
    assert manager.status(item) == "inactive"
    settings = _read_settings(root / "settings.json")
    assert "nemesis charm" not in settings["enabled_configs"]
    assert not (root / "configs" / "nemesis charm.json").exists()

    # --- Réactivation ---
    again = manager.activate(item, fm)
    assert again.ok and again.selected
    assert manager.status(item) == "active"


# ---------------------------------------------------------------------- #
# Clear Configs (sélection de configs du dossier actif de Fleasion)
# ---------------------------------------------------------------------- #

def _fake_recycler(moved: list, fail_on: str | None = None):
    """A recycler that records file names and unlinks them (like a Recycle
    Bin move would); raises when ``fail_on`` is its file name."""
    def recycler(path: Path) -> None:
        if fail_on is not None and path.name == fail_on:
            raise OSError(f"Impossible de déplacer « {path.name} » vers la Corbeille (erreur 0).")
        moved.append(path.stem)
        path.unlink()
    return recycler


def test_list_configs_uses_real_names(tmp_path: Path) -> None:
    """list_configs returns the real file names of configs/, never a
    hard-coded list, and ignores non-json files."""
    root = _fleasion_root(tmp_path)
    (root / "configs" / "nemesis charm.json").write_text("{}", encoding="utf-8")
    (root / "configs" / "Crosskey.json").write_text("{}", encoding="utf-8")
    (root / "configs" / "notes.txt").write_text("x", encoding="utf-8")
    manager = FleasionManager(root / "config", BackupManager(tmp_path / "backups"))

    assert manager.list_configs() == ["Crosskey", "nemesis charm"]


def test_clear_configs_moves_selected_and_updates_settings(tmp_path: Path) -> None:
    """Seules les configs sélectionnées partent vers la Corbeille ;
    settings.json est sauvegardé ; enabled_configs et last_config sont
    nettoyés ; les autres configs et la bibliothèque sont intactes."""
    root = _fleasion_root(tmp_path, enabled=["nemesis charm", "Crosskey", "Keep"])
    (root / "configs" / "nemesis charm.json").write_text("{}", encoding="utf-8")
    (root / "configs" / "Crosskey.json").write_text("{}", encoding="utf-8")
    (root / "configs" / "Keep.json").write_text("{}", encoding="utf-8")
    # Un marqueur hors configs/ ne doit jamais être touché.
    (root / "Fleasion.exe").write_text("app", encoding="utf-8")
    backups_dir = tmp_path / "backups"
    backup_manager = BackupManager(backups_dir)
    manager = FleasionManager(root / "config", backup_manager)
    moved: list[str] = []

    outcome = manager.clear_configs(
        ["nemesis charm", "Crosskey"], recycler=_fake_recycler(moved)
    )

    assert outcome.ok
    assert sorted(outcome.moved) == ["Crosskey", "nemesis charm"]
    assert sorted(moved) == sorted(outcome.moved)
    assert not (root / "configs" / "nemesis charm.json").exists()
    assert not (root / "configs" / "Crosskey.json").exists()
    # La config non sélectionnée est intacte.
    assert (root / "configs" / "Keep.json").exists()
    # Rien hors configs/ n'a été touché.
    assert (root / "Fleasion.exe").read_text(encoding="utf-8") == "app"
    assert outcome.selection_updated
    # settings.json a été sauvegardé avant modification.
    infos = backup_manager.list_backups()
    assert any(
        any(p.name == "settings.json" for p in info.files) for info in infos
    ), "settings.json non sauvegardé"
    settings = _read_settings(root / "settings.json")
    assert settings["enabled_configs"] == ["Keep"]
    assert settings["last_config"] is None  # pointait vers nemesis charm
    assert settings["theme"] == "Dark"


def test_clear_configs_no_selection_is_noop(tmp_path: Path) -> None:
    root = _fleasion_root(tmp_path, enabled=["Crosskey"])
    (root / "configs" / "Crosskey.json").write_text("{}", encoding="utf-8")
    manager = FleasionManager(root / "config", BackupManager(tmp_path / "backups"))

    outcome = manager.clear_configs([], recycler=_fake_recycler([]))
    assert outcome.ok
    assert outcome.moved == []
    assert (root / "configs" / "Crosskey.json").exists()


def test_clear_configs_refuses_invalid_name(tmp_path: Path) -> None:
    """Un nom qui sortirait du dossier configs/ est refusé."""
    root = _fleasion_root(tmp_path, enabled=["Crosskey"])
    (root / "configs" / "Crosskey.json").write_text("{}", encoding="utf-8")
    manager = FleasionManager(root / "config", BackupManager(tmp_path / "backups"))
    moved: list[str] = []

    outcome = manager.clear_configs(["../evil", "a/b"], recycler=_fake_recycler(moved))
    assert not outcome.ok
    assert outcome.errors
    assert moved == []
    assert (root / "configs" / "Crosskey.json").exists()


def test_clear_configs_without_structure_is_refused(tmp_path: Path) -> None:
    configured = tmp_path / "config"
    configured.mkdir()
    (configured / "nemesis charm.json").write_text("{}", encoding="utf-8")
    manager = FleasionManager(configured, BackupManager(tmp_path / "backups"))

    outcome = manager.clear_configs(["nemesis charm"], recycler=_fake_recycler([]))
    assert not outcome.ok
    assert outcome.errors
    assert outcome.moved == []
    assert (configured / "nemesis charm.json").exists()


def test_clear_configs_failure_aborts_and_keeps_settings(tmp_path: Path) -> None:
    """Un échec de Corbeille interrompt l'opération : la sélection n'est
    PAS modifiée et les fichiers restent récupérables."""
    root = _fleasion_root(tmp_path, enabled=["Crosskey", "nemesis charm"])
    (root / "configs" / "Crosskey.json").write_text("{}", encoding="utf-8")
    (root / "configs" / "nemesis charm.json").write_text("{}", encoding="utf-8")
    manager = FleasionManager(root / "config", BackupManager(tmp_path / "backups"))
    moved: list[str] = []

    outcome = manager.clear_configs(
        ["Crosskey", "nemesis charm"],
        recycler=_fake_recycler(moved, fail_on="nemesis charm.json"),
    )
    assert not outcome.ok
    assert any("interrompu" in e for e in outcome.errors)
    assert moved == ["Crosskey"]
    assert not (root / "configs" / "Crosskey.json").exists()
    assert (root / "configs" / "nemesis charm.json").exists()
    # La sélection n'a PAS été vidée.
    settings = _read_settings(root / "settings.json")
    assert settings["enabled_configs"] == ["Crosskey", "nemesis charm"]


def test_clear_configs_moves_into_internal_trash(tmp_path: Path) -> None:
    """Clear Configs utilise la **Corbeille interne de l'application** :
    les fichiers sont réellement présents dans trash/payload/, settings.json
    est sauvegardé, et la sélection est nettoyée puis vérifiée."""
    root = _fleasion_root(tmp_path, enabled=["nemesis charm", "Crosskey", "Keep"])
    (root / "configs" / "nemesis charm.json").write_text("{}", encoding="utf-8")
    (root / "configs" / "Crosskey.json").write_text("{}", encoding="utf-8")
    (root / "configs" / "Keep.json").write_text("{}", encoding="utf-8")
    trash = Trash(tmp_path / "trash")
    manager = FleasionManager(root / "config", BackupManager(tmp_path / "backups"))

    outcome = manager.clear_configs(["nemesis charm", "Crosskey"], trash=trash)

    assert outcome.ok
    assert sorted(outcome.moved) == ["Crosskey", "nemesis charm"]
    assert not (root / "configs" / "nemesis charm.json").exists()
    assert not (root / "configs" / "Crosskey.json").exists()
    assert (root / "configs" / "Keep.json").exists()

    # Le contenu est RÉELLEMENT dans la Corbeille interne (payload/).
    entries = trash.list_entries()
    assert len(entries) == 2
    payloads = {}
    for e in entries:
        payloads[e.name] = (e.folder / "payload" / e.name).is_file()
    assert payloads == {"Crosskey.json": True, "nemesis charm.json": True}
    # was_active reflète l'état avant suppression (les deux étaient actifs).
    by_name = {e.name: e for e in entries}
    assert by_name["nemesis charm.json"].was_active is True
    assert by_name["Crosskey.json"].was_active is True

    assert outcome.selection_updated
    settings = _read_settings(root / "settings.json")
    assert settings["enabled_configs"] == ["Keep"]
    assert settings["last_config"] is None


def test_clear_configs_restore_from_internal_trash(tmp_path: Path) -> None:
    """Une config Fleasion supprimée via Clear Configs peut être restaurée
    depuis la Corbeille interne à son emplacement d'origine (configs/),
    sans réactivation automatique."""
    root = _fleasion_root(tmp_path, enabled=["Keyper"])
    (root / "configs" / "Keyper.json").write_text('{"k": 1}', encoding="utf-8")
    trash = Trash(tmp_path / "trash")
    manager = FleasionManager(root / "config", BackupManager(tmp_path / "backups"))

    outcome = manager.clear_configs(["Keyper"], trash=trash)
    assert outcome.ok
    assert not (root / "configs" / "Keyper.json").exists()

    entry = trash.list_entries()[0]
    restored = trash.restore(
        entry, allowed_roots=[root / "configs"]
    )
    assert restored == root / "configs" / "Keyper.json"
    assert (root / "configs" / "Keyper.json").is_file()
    assert trash.list_entries() == []
    # Aucune réactivation automatique : la sélection reste vide.
    settings = _read_settings(root / "settings.json")
    assert settings["enabled_configs"] == []

def _fake_process(tmp_path: Path) -> list[dict]:
    """Un processus Fleasion simulé avec un exécutable réellement présent
    sur le disque (le garde-fou refuse un exe inexistant)."""
    exe = tmp_path / "Fake" / "Fleasion.exe"
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.write_bytes(b"MZ")
    return [{"pid": 4242, "exe": str(exe), "cmd": f'"{exe}"'}]


def _fake_powershell_run(stdout: str):
    import types

    import app.fleasion_restart as fr

    fake = types.SimpleNamespace(returncode=0, stdout=stdout, stderr="")
    return lambda *a, **k: fake


def test_find_fleasion_processes_uses_image_name(tmp_path, monkeypatch) -> None:
    """Le vrai Fleasion (onefile élevé) n'expose que son nom d'image : la
    détection l'accepte et résout son exécutable via le profil utilisateur."""
    import json as _json

    import app.fleasion_restart as fr

    real_exe = tmp_path / "Fleasion-v2.1.0 (1).exe"
    real_exe.write_bytes(b"MZ")
    rows = [
        {"pid": 612, "name": "Fleasion-v2.1.0 (1).exe", "exe": None, "cmd": None},
        # Le processus qui exécute la requête ne doit jamais être retenu.
        {"pid": 9001, "name": "powershell.exe",
         "exe": r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
         "cmd": "powershell ... fleasion ..."},
    ]
    monkeypatch.setattr(fr, "_TESTS_DISABLE_REAL", False, raising=False)
    monkeypatch.setattr(
        fr.subprocess, "run",
        _fake_powershell_run(_json.dumps(rows)),
    )
    monkeypatch.setattr(fr, "_search_user_profile", lambda name: real_exe)

    procs = fr.find_fleasion_processes()
    assert procs == [{"pid": 612, "exe": str(real_exe), "name": "Fleasion-v2.1.0 (1).exe", "cmd": None}]


def test_find_fleasion_processes_rejects_self_matches(tmp_path, monkeypatch) -> None:
    """Shells/interpréteurs dont la ligne de commande contient « fleasion »
    (le texte de la requête) ne sont jamais confondus avec Fleasion."""
    import json as _json

    import app.fleasion_restart as fr

    rows = [
        {"pid": 1, "name": "bash.exe",
         "exe": r"C:\Program Files\Git\bin\bash.exe",
         "cmd": '"bash.exe" -c "... from app import fleasion_restart ..."'},
        {"pid": 2, "name": "python.exe",
         "exe": r"C:\Python\python.exe", "cmd": "python main.py"},
    ]
    monkeypatch.setattr(fr, "_TESTS_DISABLE_REAL", False, raising=False)
    monkeypatch.setattr(fr.subprocess, "run", _fake_powershell_run(_json.dumps(rows)))

    assert fr.find_fleasion_processes() == []


def test_find_fleasion_processes_enumeration_failure(monkeypatch) -> None:
    import app.fleasion_restart as fr

    def _boom(*a, **k):
        raise OSError("boom")

    monkeypatch.setattr(fr, "_TESTS_DISABLE_REAL", False, raising=False)
    monkeypatch.setattr(fr.subprocess, "run", _boom)
    assert fr.find_fleasion_processes() is None


def test_hot_restart_refuses_without_existing_exe(tmp_path, monkeypatch) -> None:
    """Fleasion « lancé » mais exécutable introuvable sur le disque : refus
    propre avant toute fermeture — jamais de faux succès."""
    import app.fleasion_restart as fr

    root = _fleasion_root(tmp_path, enabled=["Crosskey"])
    (root / "logs").mkdir()
    (root / "logs" / "fleasion.log").write_text("x\n", encoding="utf-8")
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")

    closed: list[list[int]] = []
    monkeypatch.setattr(
        fr, "find_fleasion_processes",
        lambda: [{"pid": 1, "exe": str(tmp_path / "missing" / "Fleasion.exe"), "cmd": None}],
    )
    monkeypatch.setattr(fr, "close_fleasion", lambda pids: closed.append(pids) or True)

    outcome = manager.activate(
        item, FileManager(BackupManager(tmp_path / "backups")), restart=True
    )
    assert outcome.ok
    assert not outcome.selected
    assert closed == []  # jamais fermé sans pouvoir relancer
    assert any("exécutable" in e.lower() for e in outcome.errors)


def test_activate_restart_confirms_through_log(tmp_path, monkeypatch) -> None:
    """Activation avec hot reload : la sélection n'est validée que si le log
    de Fleasion (après redémarrage) confirme « [Config] Enabled: <nom> »."""
    import app.fleasion_restart as fr

    root = _fleasion_root(tmp_path, enabled=["Crosskey"])
    (root / "logs").mkdir()
    (root / "logs" / "fleasion.log").write_text("[Cache] started\n", encoding="utf-8")
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")

    monkeypatch.setattr(fr, "find_fleasion_processes", lambda: _fake_process(tmp_path))
    monkeypatch.setattr(fr, "close_fleasion", lambda pids: True)
    monkeypatch.setattr(fr, "start_fleasion", lambda exe: True)
    monkeypatch.setattr(
        fr, "wait_for_log_event",
        lambda *a, **k: ["[Config] Enabled: nemesis charm"],
    )

    outcome = manager.activate(
        item, FileManager(BackupManager(tmp_path / "backups")), restart=True
    )
    assert outcome.ok
    assert outcome.selected  # confirmé par le log, pas seulement par le JSON
    assert outcome.errors == []
    settings = _read_settings(root / "settings.json")
    assert "nemesis charm" in settings["enabled_configs"]


def test_activate_restart_unconfirmed_no_false_success(tmp_path, monkeypatch) -> None:
    """Fleasion redémarré mais le log ne confirme pas : jamais « ACTIF »."""
    import app.fleasion_restart as fr

    root = _fleasion_root(tmp_path, enabled=["Crosskey"])
    (root / "logs").mkdir()
    (root / "logs" / "fleasion.log").write_text("[Cache] started\n", encoding="utf-8")
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")

    monkeypatch.setattr(fr, "find_fleasion_processes", lambda: _fake_process(tmp_path))
    monkeypatch.setattr(fr, "close_fleasion", lambda pids: True)
    monkeypatch.setattr(fr, "start_fleasion", lambda exe: True)
    monkeypatch.setattr(fr, "wait_for_log_event", lambda *a, **k: [])

    outcome = manager.activate(
        item, FileManager(BackupManager(tmp_path / "backups")), restart=True
    )
    assert outcome.ok  # les fichiers sont copiés
    assert not outcome.selected  # mais la sélection n'est PAS confirmée
    assert outcome.needs_manual_selection
    assert outcome.errors  # une erreur claire est remontée


def test_activate_restart_fleasion_not_running(tmp_path, monkeypatch) -> None:
    """Fleasion non lancé : rien à redémarrer ; la sélection enregistrée sera
    appliquée à son prochain démarrage (aucune fausse erreur)."""
    import app.fleasion_restart as fr

    root = _fleasion_root(tmp_path, enabled=["Crosskey"])
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")

    monkeypatch.setattr(fr, "find_fleasion_processes", lambda: [])

    outcome = manager.activate(
        item, FileManager(BackupManager(tmp_path / "backups")), restart=True
    )
    assert outcome.ok
    assert outcome.selected
    assert outcome.errors == []


def test_activate_restart_close_failure_no_false_success(tmp_path, monkeypatch) -> None:
    import app.fleasion_restart as fr

    root = _fleasion_root(tmp_path, enabled=["Crosskey"])
    (root / "logs").mkdir()
    (root / "logs" / "fleasion.log").write_text("x\n", encoding="utf-8")
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")

    monkeypatch.setattr(fr, "find_fleasion_processes", lambda: _fake_process(tmp_path))
    monkeypatch.setattr(fr, "close_fleasion", lambda pids: False)

    outcome = manager.activate(
        item, FileManager(BackupManager(tmp_path / "backups")), restart=True
    )
    assert outcome.ok
    assert not outcome.selected
    assert outcome.needs_manual_selection
    assert any("fermer" in e.lower() for e in outcome.errors)


def test_activate_restart_enumeration_failure(tmp_path, monkeypatch) -> None:
    """État inconnu (énumération impossible) : pas de faux succès."""
    import app.fleasion_restart as fr

    root = _fleasion_root(tmp_path, enabled=["Crosskey"])
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")

    monkeypatch.setattr(fr, "find_fleasion_processes", lambda: None)

    outcome = manager.activate(
        item, FileManager(BackupManager(tmp_path / "backups")), restart=True
    )
    assert outcome.ok
    assert not outcome.selected
    assert outcome.errors


def test_activate_restart_exe_unrecoverable(tmp_path, monkeypatch) -> None:
    """Fleasion lancé mais exécutable introuvable : refus propre avant toute
    fermeture (on ne laisse jamais Fleasion fermé sans pouvoir le relancer)."""
    import app.fleasion_restart as fr

    root = _fleasion_root(tmp_path, enabled=["Crosskey"])
    (root / "logs").mkdir()
    (root / "logs" / "fleasion.log").write_text("x\n", encoding="utf-8")
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")

    closed = []
    monkeypatch.setattr(
        fr, "find_fleasion_processes",
        lambda: [{"pid": 1, "exe": None, "cmd": None}],
    )
    monkeypatch.setattr(fr, "close_fleasion", lambda pids: closed.append(pids) or True)

    outcome = manager.activate(
        item, FileManager(BackupManager(tmp_path / "backups")), restart=True
    )
    assert outcome.ok
    assert not outcome.selected
    assert closed == []  # jamais fermé sans pouvoir relancer
    assert any("exécutable" in e.lower() for e in outcome.errors)


def test_deactivate_restart_confirmed(tmp_path, monkeypatch) -> None:
    """Désactivation avec hot reload : confirmée si le log de Fleasion ne
    charge plus la configuration (les autres restent actives)."""
    import app.fleasion_restart as fr

    root = _fleasion_root(tmp_path, enabled=["nemesis charm", "Crosskey"])
    (root / "configs" / "nemesis charm.json").write_text("{}", encoding="utf-8")
    (root / "logs").mkdir()
    (root / "logs" / "fleasion.log").write_text("[Cache] started\n", encoding="utf-8")
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")

    monkeypatch.setattr(fr, "find_fleasion_processes", lambda: _fake_process(tmp_path))
    monkeypatch.setattr(fr, "close_fleasion", lambda pids: True)
    monkeypatch.setattr(fr, "start_fleasion", lambda exe: True)
    monkeypatch.setattr(
        fr, "wait_for_log_event",
        lambda *a, **k: ["[Config] Enabled: Crosskey"],
    )

    outcome = manager.deactivate(
        item, FileManager(BackupManager(tmp_path / "backups")), restart=True
    )
    assert outcome.ok
    assert outcome.selection_cleared
    assert outcome.errors == []
    settings = _read_settings(root / "settings.json")
    assert "nemesis charm" not in settings["enabled_configs"]
    assert "Crosskey" in settings["enabled_configs"]  # les autres intactes


def test_deactivate_restart_re_enabled_fails(tmp_path, monkeypatch) -> None:
    """Fleasion recharge quand même la configuration après redémarrage :
    la désactivation n'est PAS confirmée (aucun faux succès)."""
    import app.fleasion_restart as fr

    root = _fleasion_root(tmp_path, enabled=["nemesis charm"])
    (root / "configs" / "nemesis charm.json").write_text("{}", encoding="utf-8")
    (root / "logs").mkdir()
    (root / "logs" / "fleasion.log").write_text("[Cache] started\n", encoding="utf-8")
    manager = _manager(root)
    item = _item(tmp_path / "lib", "nemesis charm")

    monkeypatch.setattr(fr, "find_fleasion_processes", lambda: _fake_process(tmp_path))
    monkeypatch.setattr(fr, "close_fleasion", lambda pids: True)
    monkeypatch.setattr(fr, "start_fleasion", lambda exe: True)
    monkeypatch.setattr(
        fr, "wait_for_log_event",
        lambda *a, **k: ["[Config] Enabled: nemesis charm"],
    )

    outcome = manager.deactivate(
        item, FileManager(BackupManager(tmp_path / "backups")), restart=True
    )
    assert not outcome.ok
    assert outcome.errors
    # La sélection a bien été retirée de settings.json, mais Fleasion
    # (source de vérité processus) ne l'a pas confirmée.
    settings = _read_settings(root / "settings.json")
    assert "nemesis charm" not in settings["enabled_configs"]


def test_hot_restart_wait_for_log_real_subprocess(tmp_path: Path) -> None:
    """Test semi-réel : un vrai sous-processus (fake Fleasion) écrit la ligne
    de log et le vrai waiter la détecte — la vérification repose sur le
    mécanisme réel de polling, pas sur un mock."""
    import subprocess
    import sys

    import app.fleasion_restart as fr

    log = tmp_path / "fleasion.log"
    log.write_text("[Cache] started\n", encoding="utf-8")
    script = tmp_path / "fake_fleasion.py"
    script.write_text(
        "import time\n"
        "from pathlib import Path\n"
        f"log = Path({str(log)!r})\n"
        "with open(log, 'a', encoding='utf-8') as f:\n"
        "    f.write('[Config] Enabled: keyst\\n')\n"
        "time.sleep(30)\n",
        encoding="utf-8",
    )
    offset = log.stat().st_size
    proc = subprocess.Popen([sys.executable, str(script)])
    try:
        lines = fr.wait_for_log_event(log, offset, ["[Config] Enabled:"], timeout=15)
        assert any("[Config] Enabled: keyst" in line for line in lines)
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_move_to_recycle_bin_real(tmp_path: Path) -> None:
    """The real Windows Recycle Bin move works and is recoverable (never a
    permanent deletion). Skipped on non-Windows systems."""
    import sys

    if sys.platform != "win32":
        import pytest

        pytest.skip("Corbeille Windows non disponible sur ce système")
    from app.recycle import move_to_recycle_bin

    target = tmp_path / "to_recycle.json"
    target.write_text("{}", encoding="utf-8")
    move_to_recycle_bin(target)
    assert not target.exists()  # déplacé (récupérable), pas supprimé


def test_restore_backup_settings_goes_to_root_not_config_dir(tmp_path: Path) -> None:
    """settings.json backups restore to the FleasionNT root, not config/."""
    root = _fleasion_root(tmp_path)
    backups_dir = tmp_path / "backups"
    backup_manager = BackupManager(backups_dir)
    manager = FleasionManager(root / "config", backup_manager)
    item = _item(tmp_path / "lib", "nemesis charm")

    manager.activate(item, FileManager(backup_manager))
    infos = backup_manager.list_backups()
    backup = next(
        info for info in infos if any(p.name == "settings.json" for p in info.files)
    )

    # Poison the current settings.json so the restore is observable.
    _write_settings(root / "settings.json", {"enabled_configs": ["poisoned"], "last_config": "poisoned"})
    manager.restore_backup(backup)

    restored = _read_settings(root / "settings.json")
    assert restored["enabled_configs"] == ["Crosskey"]
    # Nothing was written into the configured config/ sub-folder.
    assert not (root / "config" / "settings.json").exists()
