"""Tests for app/trash.py — the application's internal trash (corbeille).

The trash stores deleted content under ``trash/<uuid>/payload/`` with
``metadata.json``; every deletion is verified before the originals are
removed, and every restore is validated against the allowed roots.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from app.backup_manager import BackupManager
from app.models import KIND_FILE, KIND_FOLDER, ConfigItem
from app.trash import PAYLOAD_DIR, TRASH_METADATA, Trash, TrashEntry, TrashError


def _write(path: Path, content: str = "{}") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _file_item(tmp_path: Path, name: str = "nemesis charm") -> ConfigItem:
    folder = tmp_path / "lib" / "Charms"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.json"
    _write(path, '{"replacement_rules": []}')
    return ConfigItem(name=name, path=path, kind=KIND_FILE, files=[path], json_files=[path])


def _entry(folder: Path, files: list[str], original: Path, kind: str = "file") -> TrashEntry:
    return TrashEntry(
        id=folder.name,
        folder=folder,
        name="test",
        kind=kind,
        original_path=original,
        created=datetime(2026, 8, 18, 10, 0, 0),
        files=files,
    )


def _payload(folder: Path) -> Path:
    return folder / PAYLOAD_DIR


def test_delete_moves_files_and_sidecars(tmp_path: Path) -> None:
    """Deleting moves the config files + interface sidecars, never the rest."""
    item = _file_item(tmp_path)
    sidecar = item.path.with_name(item.path.stem + ".image.json")
    _write(sidecar)
    (item.path.parent / "other.json").write_text("{}", encoding="utf-8")

    trash = Trash(tmp_path / "trash")
    entry = trash.delete_item(item)

    assert not item.path.exists()
    assert not sidecar.exists()
    # The rest of the folder is untouched.
    assert (item.path.parent / "other.json").exists()
    assert entry.kind == "file"
    assert set(entry.files) == {"nemesis charm.json", "nemesis charm.image.json"}
    assert entry.original_path == item.path
    # Le contenu est réellement présent dans la Corbeille (payload/).
    assert (_payload(entry.folder) / "nemesis charm.json").is_file()
    assert trash.list_entries() == [entry]


def test_delete_folder_config_moves_folder_content(tmp_path: Path) -> None:
    folder = tmp_path / "lib" / "Texture packs"
    folder.mkdir(parents=True)
    _write(folder / "config.json")
    _write(folder / "image.json")  # sidecar inside the folder
    (folder / "model.obj").write_text("v 0 0 0", encoding="utf-8")
    item = ConfigItem(
        name="Texture packs",
        path=folder,
        kind=KIND_FOLDER,
        files=[folder / "config.json", folder / "model.obj"],
        json_files=[folder / "config.json"],
    )

    trash = Trash(tmp_path / "trash")
    entry = trash.delete_item(item)
    assert not (folder / "config.json").exists()
    assert entry.kind == "folder"
    assert set(entry.files) == {"config.json", "image.json", "model.obj"}
    assert (_payload(entry.folder) / "config.json").is_file()
    assert (_payload(entry.folder) / "image.json").is_file()


def test_delete_item_without_files_raises(tmp_path: Path) -> None:
    item = ConfigItem(
        name="ghost",
        path=tmp_path / "ghost.json",
        kind=KIND_FILE,
        files=[tmp_path / "ghost.json"],
        json_files=[tmp_path / "ghost.json"],
    )
    trash = Trash(tmp_path / "trash")
    with pytest.raises(TrashError):
        trash.delete_item(item)


def test_restore_puts_files_back(tmp_path: Path) -> None:
    item = _file_item(tmp_path)
    sidecar = item.path.with_name(item.path.stem + ".image.json")
    _write(sidecar)
    trash = Trash(tmp_path / "trash")
    entry = trash.delete_item(item)

    restored = trash.restore(entry)
    assert restored == item.path
    assert item.path.exists()
    assert sidecar.exists()
    assert trash.list_entries() == []
    # Content intact.
    assert item.path.read_text(encoding="utf-8") == '{"replacement_rules": []}'


def test_restore_folder_config(tmp_path: Path) -> None:
    folder = tmp_path / "lib" / "Texture packs"
    folder.mkdir(parents=True)
    _write(folder / "config.json")
    item = ConfigItem(
        name="Texture packs",
        path=folder,
        kind=KIND_FOLDER,
        files=[folder / "config.json"],
        json_files=[folder / "config.json"],
    )
    trash = Trash(tmp_path / "trash")
    entry = trash.delete_item(item)

    restored = trash.restore(entry)
    assert restored == folder
    assert (folder / "config.json").exists()


def test_restore_backs_up_existing_target(tmp_path: Path) -> None:
    item = _file_item(tmp_path)
    trash = Trash(tmp_path / "trash")
    entry = trash.delete_item(item)
    # A new file appears at the original location.
    item.path.write_text('{"new": true}', encoding="utf-8")
    backups = BackupManager(tmp_path / "backups")

    trash.restore(entry, backup_before_overwrite=True, backup_manager=backups)
    # The restored content wins, the new file was backed up.
    assert item.path.read_text(encoding="utf-8") == '{"replacement_rules": []}'
    infos = backups.list_backups()
    assert infos
    backed = infos[0].folder / "nemesis charm.json"
    assert backed.read_text(encoding="utf-8") == '{"new": true}'


def test_restore_refuses_path_escape(tmp_path: Path) -> None:
    """A corrupted metadata file cannot make restore write outside the
    recorded original location (zip-slip guard)."""
    folder = tmp_path / "trash" / "entry"
    folder.mkdir(parents=True)
    escape = tmp_path / "trash" / "evil.json"  # resolves outside the entry folder
    escape.write_text("x", encoding="utf-8")
    entry = _entry(folder, files=["../evil.json"], original=tmp_path / "dest" / "ok.json")

    trash = Trash(tmp_path / "trash")
    with pytest.raises(TrashError):
        trash.restore(entry)
    assert not (tmp_path / "dest" / "evil.json").exists()
    assert not (tmp_path / "evil.json").exists()


def test_destroy_permanently_deletes(tmp_path: Path) -> None:
    item = _file_item(tmp_path)
    trash = Trash(tmp_path / "trash")
    entry = trash.delete_item(item)
    assert trash.list_entries()

    trash.destroy(entry)
    assert trash.list_entries() == []
    assert not entry.folder.exists()


def test_empty_deletes_all(tmp_path: Path) -> None:
    trash = Trash(tmp_path / "trash")
    for name in ("alpha", "beta"):
        trash.delete_item(_file_item(tmp_path, name))
    assert len(trash.list_entries()) == 2

    assert trash.empty() == 2
    assert trash.list_entries() == []


def test_delete_fills_category_from_path(tmp_path: Path) -> None:
    """The entry's category is derived from its path and survives reload."""
    folder = tmp_path / "lib" / "rivals skins" / "Primary" / "Assault Rifle"
    folder.mkdir(parents=True)
    path = folder / "ak-47.json"
    _write(path)
    item = ConfigItem(
        name="ak-47", path=path, kind=KIND_FILE, files=[path], json_files=[path]
    )

    trash = Trash(tmp_path / "trash")
    entry = trash.delete_item(item)
    assert entry.category == "primary"

    # The category is stored in the metadata and survives a reload.
    entries = Trash(tmp_path / "trash").list_entries()
    assert entries[0].category == "primary"
    assert entries[0].weapon is None


def test_trash_persists_across_instances(tmp_path: Path) -> None:
    """The trash never disappears: a fresh instance sees the same entries
    (simulates an application restart)."""
    item = _file_item(tmp_path)
    Trash(tmp_path / "trash").delete_item(item)

    entries = Trash(tmp_path / "trash").list_entries()
    assert len(entries) == 1
    assert entries[0].name == "nemesis charm"
    assert entries[0].category is None
    assert entries[0].weapon is None
    assert (_payload(entries[0].folder) / "nemesis charm.json").is_file()
    assert (entries[0].folder / TRASH_METADATA).is_file()


# ---------------------------------------------------------------------- #
# Nouveaux tests (Étape 11 — Corbeille interne)
# ---------------------------------------------------------------------- #

def test_metadata_is_complete(tmp_path: Path) -> None:
    """metadata.json contient version, id UUID, original_path/name,
    item_type, deleted_at et size ; id ≠ nom original."""
    item = _file_item(tmp_path, "Keyper")
    _write(item.path, '{"a": 1}')
    expected_size = item.path.stat().st_size
    trash = Trash(tmp_path / "trash")
    entry = trash.delete_item(item)

    data = json.loads((entry.folder / TRASH_METADATA).read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["id"] == entry.id
    assert data["id"] != "Keyper"  # identifiant unique, pas le nom
    assert data["original_path"] == str(item.path)
    assert data["original_name"] == "Keyper"
    assert data["item_type"] == "file"
    assert data["deleted_at"]
    assert data["size"] == expected_size
    assert data["files"] == ["Keyper.json"]


def test_uuids_are_unique(tmp_path: Path) -> None:
    trash = Trash(tmp_path / "trash")
    ids = {trash.delete_item(_file_item(tmp_path, n)).id for n in ("a", "b", "c")}
    assert len(ids) == 3


def test_delete_path_file(tmp_path: Path) -> None:
    """delete_path déplace un fichier seul (clic droit sur une config)."""
    file = tmp_path / "lib" / "Charms" / "flossswap.json"
    _write(file)
    trash = Trash(tmp_path / "trash")
    entry = trash.delete_path(file)
    assert entry.kind == "file"
    assert not file.exists()
    assert (_payload(entry.folder) / "flossswap.json").is_file()


def test_delete_path_directory_preserves_structure(tmp_path: Path) -> None:
    """delete_path déplace tout un dossier (catégorie/arme) en conservant
    la structure relative pour une restauration exacte."""
    folder = tmp_path / "lib" / "rivals skins" / "Primary" / "Assault Rifle"
    _write(folder / "ak-47.json")
    _write(folder / "sub" / "extra.json")
    trash = Trash(tmp_path / "trash")

    entry = trash.delete_path(folder)
    assert entry.kind == "folder"
    assert not folder.exists()
    assert (_payload(entry.folder) / "ak-47.json").is_file()
    assert (_payload(entry.folder) / "sub" / "extra.json").is_file()

    restored = trash.restore(entry, allowed_roots=[tmp_path / "lib"])
    assert restored == folder
    assert (folder / "ak-47.json").is_file()
    assert (folder / "sub" / "extra.json").is_file()


def test_delete_path_missing_raises(tmp_path: Path) -> None:
    trash = Trash(tmp_path / "trash")
    with pytest.raises(TrashError):
        trash.delete_path(tmp_path / "ghost.json")


def test_restore_destination_exists_detects_conflict(tmp_path: Path) -> None:
    """destination_exists signale un conflit sans rien écrire."""
    item = _file_item(tmp_path)
    trash = Trash(tmp_path / "trash")
    entry = trash.delete_item(item)
    assert not trash.destination_exists(entry)  # destination libre

    item.path.write_text('{"new": true}', encoding="utf-8")
    assert trash.destination_exists(entry)
    # Rien n'a été écrasé.
    assert item.path.read_text(encoding="utf-8") == '{"new": true}'


def test_restore_keep_both_never_overwrites(tmp_path: Path) -> None:
    """« Garder les deux » restaure à côté sans écraser l'existant."""
    item = _file_item(tmp_path)
    trash = Trash(tmp_path / "trash")
    entry = trash.delete_item(item)
    # Un nouveau fichier apparaît à l'emplacement d'origine.
    item.path.write_text('{"new": true}', encoding="utf-8")

    restored = trash.restore(entry, mode="keep_both")
    assert restored != item.path
    assert restored.exists()
    # L'existant est intact, le restauré est à côté.
    assert item.path.read_text(encoding="utf-8") == '{"new": true}'
    assert restored.read_text(encoding="utf-8") == '{"replacement_rules": []}'
    assert trash.list_entries() == []


def test_restore_refuses_outside_allowed_roots(tmp_path: Path) -> None:
    """Une restauration vers un chemin hors des dossiers autorisés est
    refusée (jamais d'écriture hors bibliothèque/Fleasion)."""
    item = _file_item(tmp_path)
    trash = Trash(tmp_path / "trash")
    entry = trash.delete_item(item)

    with pytest.raises(TrashError):
        trash.restore(entry, allowed_roots=[tmp_path / "elsewhere"])
    # Rien n'a été restauré, l'entrée reste disponible.
    assert trash.list_entries() == [entry]
    assert not item.path.exists()


def test_was_active_recorded(tmp_path: Path) -> None:
    """Clear Configs conserve l'état actif (was_active) pour une
    restauration exacte — sans jamais réactiver automatiquement."""
    file = tmp_path / "fleasion" / "configs" / "Keyper.json"
    _write(file)
    trash = Trash(tmp_path / "trash")

    trash.delete_path(file, was_active=True)
    entries = trash.list_entries()
    assert entries[0].was_active is True
    data = json.loads((entries[0].folder / TRASH_METADATA).read_text(encoding="utf-8"))
    assert data["was_active"] is True


def test_real_fixture_delete_restore_destroy(tmp_path: Path) -> None:
    """Test réel contrôlé sur bibliothèque temporaire : suppression →
    présence réelle dans la Corbeille → restauration → retour exact →
    suppression définitive → disparition. Aucun fichier réel touché."""
    lib = tmp_path / "Rivals configs" / "Charms"
    _write(lib / "nemesis charm.json")
    trash = Trash(tmp_path / "trash")

    # 1. Suppression → la Corbeille contient réellement le fichier.
    entry = trash.delete_path(lib / "nemesis charm.json")
    assert not (lib / "nemesis charm.json").exists()
    assert (_payload(entry.folder) / "nemesis charm.json").is_file()
    assert trash.list_entries() == [entry]

    # 2. Restauration → retour exact, entrée retirée.
    restored = trash.restore(entry, allowed_roots=[tmp_path / "Rivals configs"])
    assert restored == lib / "nemesis charm.json"
    assert (lib / "nemesis charm.json").is_file()
    assert trash.list_entries() == []

    # 3. Suppression définitive → disparition réelle.
    entry2 = trash.delete_path(lib / "nemesis charm.json")
    trash.destroy(entry2)
    assert trash.list_entries() == []
    assert not entry2.folder.exists()
