"""Tests for app/backup_manager.py."""

from __future__ import annotations

from pathlib import Path

from app.backup_manager import BackupManager


def test_create_and_list(tmp_path: Path) -> None:
    root = tmp_path / "backups"
    manager = BackupManager(root)

    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "a.json").write_text("{}", encoding="utf-8")
    (source_dir / "b.json").write_text("{}", encoding="utf-8")

    folder = manager.create_backup([source_dir / "a.json", source_dir / "b.json"])
    assert folder.is_dir()
    assert (folder / "a.json").exists()
    assert (folder / "b.json").exists()

    backups = manager.list_backups()
    assert len(backups) == 1
    assert backups[0].file_count == 2
    assert backups[0].folder == folder


def test_create_backup_no_files_raises(tmp_path: Path) -> None:
    manager = BackupManager(tmp_path / "backups")
    try:
        manager.create_backup([tmp_path / "ghost.json", tmp_path / "other.json"])
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for empty backup")


def test_unique_timestamps(tmp_path: Path) -> None:
    manager = BackupManager(tmp_path / "backups")
    f = tmp_path / "f.json"
    f.write_text("{}", encoding="utf-8")
    first = manager.create_backup([f])
    # Force the same timestamp twice by reusing the name pattern.
    duplicate = first.parent / first.name
    duplicate.mkdir(exist_ok=True)
    second = manager.create_backup([f])
    assert second != first
    assert second.is_dir()


def test_restore(tmp_path: Path) -> None:
    manager = BackupManager(tmp_path / "backups")
    src = tmp_path / "src"
    src.mkdir()
    (src / "skin.json").write_text('{"v": 1}', encoding="utf-8")
    backup_folder = manager.create_backup([src / "skin.json"])

    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / "skin.json").write_text('{"v": 2}', encoding="utf-8")  # overwritten later

    backup = manager.list_backups()[0]
    errors = manager.restore(backup, dest)
    assert errors == []
    assert (dest / "skin.json").read_text(encoding="utf-8") == '{"v": 1}'


def test_restore_unwritable_dest_reports_error(tmp_path: Path) -> None:
    manager = BackupManager(tmp_path / "backups")
    src = tmp_path / "src"
    src.mkdir()
    f = src / "skin.json"
    f.write_text("{}", encoding="utf-8")
    manager.create_backup([f])

    backup = manager.list_backups()[0]
    # The destination "folder" is actually a file: restore must fail cleanly.
    dest = tmp_path / "dest"
    dest.write_text("not a folder", encoding="utf-8")
    errors = manager.restore(backup, dest)
    assert errors


def test_restore_missing_backup_file_simply_skipped(tmp_path: Path) -> None:
    """A damaged backup (missing file) is skipped without crashing."""
    manager = BackupManager(tmp_path / "backups")
    src = tmp_path / "src"
    src.mkdir()
    f = src / "skin.json"
    f.write_text("{}", encoding="utf-8")
    backup_folder = manager.create_backup([f])
    (backup_folder / "skin.json").unlink()

    backup = manager.list_backups()[0]
    assert backup.files == []
    dest = tmp_path / "dest"
    errors = manager.restore(backup, dest)
    assert errors == []
