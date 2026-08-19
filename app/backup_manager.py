"""Backup management.

Before a configuration is activated, files that would be overwritten in the
Fleasion config folder are copied into a timestamped backup directory:

    %APPDATA%\\RivalsConfigManager\\backups\\20260817_183000\\<file names>

The user can restore any backup from the Settings page.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class BackupInfo:
    folder: Path
    name: str
    created: datetime
    files: list[Path]

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def label(self) -> str:
        return self.created.strftime("%d/%m/%Y %H:%M:%S")


class BackupManager:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    def create_backup(self, files: list[Path]) -> Path:
        """Copy ``files`` into a new timestamped backup folder.

        Returns the backup folder. Files keep their original names, so a
        backup can be restored by copying them back.
        """
        files = [f for f in files if f.exists()]
        if not files:
            raise ValueError("Aucun fichier à sauvegarder.")

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = self.root / stamp
        suffix = 2
        while folder.exists():
            folder = self.root / f"{stamp}_{suffix}"
            suffix += 1
        folder.mkdir(parents=True, exist_ok=False)

        for source in files:
            try:
                shutil.copy2(source, folder / source.name)
            except OSError:
                # A file that cannot be backed up must not block the copy:
                # it will simply be overwritten (see FileManager).
                pass
        return folder

    # ------------------------------------------------------------------ #
    def list_backups(self) -> list[BackupInfo]:
        """List existing backups, most recent first."""
        infos: list[BackupInfo] = []
        if not self.root.is_dir():
            return infos
        for folder in sorted(self.root.iterdir(), reverse=True):
            if not folder.is_dir():
                continue
            try:
                created = datetime.strptime(folder.name, "%Y%m%d_%H%M%S")
            except ValueError:
                created = datetime.fromtimestamp(folder.stat().st_mtime)
            files = sorted(
                (p for p in folder.iterdir() if p.is_file()),
                key=lambda p: p.name.lower(),
            )
            infos.append(BackupInfo(folder=folder, name=folder.name, created=created, files=files))
        return infos

    # ------------------------------------------------------------------ #
    def restore(self, backup: BackupInfo, dest_dir: Path) -> list[str]:
        """Copy the backup files back into ``dest_dir``.

        Returns a list of error messages (empty on success). Files already
        present in ``dest_dir`` are simply overwritten.
        """
        errors: list[str] = []
        dest = Path(dest_dir)
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return [f"Impossible de créer « {dest} » : {exc.strerror or exc}"]

        for source in backup.files:
            try:
                shutil.copy2(source, dest / source.name)
            except OSError as exc:
                errors.append(f"Impossible de restaurer « {source.name} » : {exc.strerror or exc}")
        return errors
