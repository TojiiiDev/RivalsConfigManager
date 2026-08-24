"""File operations: activating a configuration.

Activation copies the files of a :class:`app.models.ConfigItem` into the
user's Fleasion config folder:

1. check the destination folder,
2. check that every source file exists,
3. validate every JSON file,
4. back up files that would be overwritten,
5. copy the files,
6. report a clear, friendly summary.

The application is a pure file manager: it never modifies Fleasion itself.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .backup_manager import BackupManager
from .i18n import t
from .json_validator import validate_files
from .models import ConfigItem


@dataclass
class CopyResult:
    ok: bool = False
    copied: list[str] = field(default_factory=list)
    backed_up: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = []
        if self.copied:
            n = len(self.copied)
            suffix = "s" if n > 1 else ""
            parts.append(
                t("outcome.copied_files", count=n, s=suffix)
            )
        if self.backed_up:
            n = len(self.backed_up)
            suffix = "s" if n > 1 else ""
            parts.append(
                t("outcome.old_files_backed_up", count=n, s=suffix)
            )
        if not parts:
            parts.append(t("outcome.nothing_copied"))
        return ", ".join(parts)


@dataclass
class RemoveResult:
    """Outcome of removing a configuration's copies from the active folder."""

    removed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        n = len(self.removed)
        if n:
            suffix = "s" if n > 1 else ""
            return t("outcome.removed_files", count=n, s=suffix)
        return t("outcome.nothing_removed")


def friendly_error(exc: OSError, name: str) -> str:
    """Turn an OS error into a message the user can understand."""
    winerror = getattr(exc, "winerror", None)
    if winerror == 32 or winerror == 33:
        return t("file_manager.locked", name=name)
    if winerror == 5 or isinstance(exc, PermissionError):
        return t("file_manager.permission", name=name)
    if winerror == 3:
        return t("file_manager.not_found", name=name)
    detail = exc.strerror or str(exc)
    return t("file_manager.copy_failed", name=name, detail=detail)


class FileManager:
    def __init__(self, backup_manager: BackupManager) -> None:
        self.backup_manager = backup_manager

    # ------------------------------------------------------------------ #
    def activate(
        self,
        item: ConfigItem,
        dest_dir: Path,
        backup_before_overwrite: bool = True,
    ) -> CopyResult:
        result = CopyResult()
        dest = Path(dest_dir)

        # 1. Destination folder -------------------------------------------------
        if not dest.exists():
            try:
                dest.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                result.errors.append(
                    t(
                        "file_manager.fleasion_dir_missing",
                        dest=dest,
                        detail=exc.strerror or exc,
                    )
                )
                return result
        if not dest.is_dir():
            result.errors.append(t("file_manager.not_a_dir", dest=dest))
            return result

        # 2. Source files must exist ---------------------------------------------
        missing = [p for p in item.files if not p.exists()]
        for o in item.objs:
            if not o.exists():
                missing.append(o)
        if missing:
            for p in missing:
                result.errors.append(t("file_manager.missing_file", path=p))
            return result

        # 3. Validate JSON files --------------------------------------------------
        ok, errors = validate_files(item.json_files)
        if not ok:
            result.errors.extend(errors)
            return result

        # 4. Back up files that would be overwritten -------------------------------
        # Destinations: the config's files plus every associated obj (which may
        # be copied under a different name, e.g. from the app's obj cache).
        dest_names = [p.name for p in item.files]
        for obj_path, obj_name in zip(item.objs, item.obj_names):
            if obj_name and obj_name not in dest_names:
                dest_names.append(obj_name)
        existing = [dest / name for name in dest_names if (dest / name).exists()]
        if backup_before_overwrite and existing:
            try:
                self.backup_manager.create_backup(existing)
                result.backed_up.extend(p.name for p in existing)
            except (OSError, ValueError):
                # Backup failure must not block the activation; files are
                # simply overwritten and the copy result still reports it.
                pass

        # 5. Copy files -------------------------------------------------------------
        for source in item.files:
            try:
                shutil.copy2(source, dest / source.name)
                result.copied.append(source.name)
            except OSError as exc:
                result.errors.append(friendly_error(exc, source.name))

        # 6. Copy every associated obj under its destination name when it is not
        # already copied (manual associations stored in the app cache).
        for obj_path, obj_name in zip(item.objs, item.obj_names):
            if obj_name and obj_name not in result.copied:
                try:
                    shutil.copy2(obj_path, dest / obj_name)
                    result.copied.append(obj_name)
                except OSError as exc:
                    result.errors.append(friendly_error(exc, obj_name))

        result.ok = not result.errors and bool(result.copied)
        return result

    # ------------------------------------------------------------------ #
    def remove_copies(
        self,
        item: ConfigItem,
        dest_dir: Path,
        backup_before_overwrite: bool = True,
    ) -> RemoveResult:
        """Remove the copies of this configuration from the active folder.

        Only files that belong to this library item are touched — the
        library keeps its originals, so the configuration can always be
        re-activated. When backup is enabled, the files are first copied
        into a backup; a backup failure aborts the removal (never delete
        without a safety net).
        """
        result = RemoveResult()
        dest = Path(dest_dir)

        names = [p.name for p in item.files]
        for obj_path, obj_name in zip(item.objs, item.obj_names):
            if obj_name and obj_name not in names:
                names.append(obj_name)
        targets = [dest / n for n in names if (dest / n).is_file()]
        if not targets:
            return result

        if backup_before_overwrite:
            try:
                self.backup_manager.create_backup(targets)
            except (OSError, ValueError):
                result.errors.append(t("file_manager.backup_before_remove_failed"))
                return result

        for target in targets:
            try:
                target.unlink()
                result.removed.append(target.name)
            except OSError as exc:
                result.errors.append(friendly_error(exc, target.name))
        return result
