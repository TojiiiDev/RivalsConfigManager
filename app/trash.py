"""Trash (corbeille) — the application's own internal trash.

« Supprimer » moves an item (a configuration, a weapon folder or a whole
category) into a persistent trash folder inside the application data
directory, **never** the Windows Recycle Bin:

    %APPDATA%\\RivalsConfigManager\\trash\\<uuid>\\
        payload\\...       the real deleted content
        metadata.json      restore information

Each entry uses a unique UUID as its folder name — the original name is
never used as an identifier. Every operation is verified: the content is
copied into ``payload/`` first, every copy is checked, the metadata is
written, and only then are the originals removed. A deletion is never
considered successful while the content is missing from the trash.

Safety rules:

* ``restore`` validates the original path against the allowed roots (the
  library and the Fleasion config folder) and refuses to write outside
  them; a zip-slip style guard also keeps every restored file inside its
  recorded destination.
* A conflict (destination already exists) is never resolved silently:
  ``destination_exists`` lets the UI ask the user, and ``restore`` takes
  an explicit ``mode`` ("replace" or "keep_both").
* ``destroy`` / ``empty`` permanently delete files — the UI must require
  explicit user confirmation before calling them.
"""

from __future__ import annotations

import json
import shutil
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .categories import category_of_path
from .config import trash_dir
from .i18n import t
from .models import ConfigItem

TRASH_METADATA = "metadata.json"
LEGACY_METADATA = "trash.json"
TRASH_VERSION = 1
PAYLOAD_DIR = "payload"


class TrashError(Exception):
    """User-facing error with a clear message."""


@dataclass
class TrashEntry:
    """One deleted item, stored in the trash (never used)."""

    id: str
    folder: Path                 # trash/<id>
    name: str
    kind: str                    # "file" or "folder"
    original_path: Path          # where it lived, for restore
    created: datetime
    files: list[str]             # file names / relative paths inside payload/
    category: str | None = None
    weapon: str | None = None
    size: int = 0                # total bytes of the deleted content
    was_active: bool | None = None  # Fleasion configs: active before delete?

    @property
    def label(self) -> str:
        return self.created.strftime("%d/%m/%Y %H:%M")

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def item_type(self) -> str:
        """« file » ou « directory » (métadonnées)."""
        return "directory" if self.kind == "folder" else "file"


class Trash:
    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else trash_dir()
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Deletion (move into the trash — never the Windows Recycle Bin)
    # ------------------------------------------------------------------ #
    def delete_item(self, item: ConfigItem) -> TrashEntry:
        """Move an item (its files + interface sidecars) into the trash."""
        sources = self._collect_sources(item)
        if not sources:
            raise TrashError(t("trash_error.no_files_to_move"))
        rel_sources = [(p, Path(p.name)) for p in sources]
        return self._store(
            rel_sources,
            name=item.name,
            original_path=item.path,
            kind="folder" if item.is_folder else "file",
            remove_tree=False,
        )

    def delete_path(
        self,
        path: Path,
        name: str | None = None,
        was_active: bool | None = None,
    ) -> TrashEntry:
        """Move a file **or a whole folder tree** into the trash.

        Used by the right-click « Supprimer » on cards (a configuration
        file, a weapon folder or a category) and by Clear Configs. For a
        folder the relative structure is preserved inside ``payload/`` so
        the restore is exact. ``was_active`` records whether a Fleasion
        config was selected before deletion (kept for an exact restore).
        """
        path = Path(path)
        if not path.exists():
            raise TrashError(t("trash_error.not_found", name=path.name))
        if path.is_file():
            rel_sources = [(path, Path(path.name))]
            kind = "file"
            remove_tree = False
        else:
            rel_sources = []
            for p in sorted(path.rglob("*")):
                if p.is_file():
                    rel_sources.append((p, p.relative_to(path)))
            # Un dossier vide est aussi supprimable : le payload est vide,
            # les métadonnées préservent le nom et le chemin d'origine.
            kind = "folder"
            remove_tree = True
        return self._store(
            rel_sources,
            name=name or path.name,
            original_path=path,
            kind=kind,
            remove_tree=remove_tree,
            was_active=was_active,
        )

    def _store(
        self,
        rel_sources: list[tuple[Path, Path]],
        name: str,
        original_path: Path,
        kind: str,
        remove_tree: bool,
        was_active: bool | None = None,
    ) -> TrashEntry:
        """Copy sources into a fresh payload/, verify every copy, write the
        metadata, and only then remove the originals. Any failure cleans up
        the partial entry and raises — nothing is left half-deleted."""
        entry_id = uuid.uuid4().hex
        folder = self.root / entry_id
        payload = folder / PAYLOAD_DIR
        payload.mkdir(parents=True, exist_ok=False)

        names: list[str] = []
        size = 0
        try:
            for source, rel in rel_sources:
                dest = payload / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, dest)
                names.append(rel.as_posix())
                size += dest.stat().st_size

            # Verify every copy before touching the originals.
            for rel in names:
                if not (payload / rel).is_file():
                    raise TrashError(
                        t("trash_error.copy_incomplete", name=Path(rel).name)
                    )

            entry = TrashEntry(
                id=entry_id,
                folder=folder,
                name=name,
                kind=kind,
                original_path=original_path,
                created=datetime.now().replace(microsecond=0),
                files=names,
                category=category_of_path(original_path),
                size=size,
                was_active=was_active,
            )
            self._write_metadata(entry)

            # Originals are removed only after the trash copy is verified.
            if remove_tree:
                shutil.rmtree(original_path)
            else:
                for source, _ in rel_sources:
                    source.unlink()
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise
        return entry

    # ------------------------------------------------------------------ #
    # Restore
    # ------------------------------------------------------------------ #
    def destination_exists(self, entry: TrashEntry) -> bool:
        """Whether the original location already holds content (a conflict
        the UI must ask about — never resolved silently)."""
        return entry.original_path.exists()

    def restore(
        self,
        entry: TrashEntry,
        backup_before_overwrite: bool = True,
        backup_manager=None,
        mode: str = "replace",
        allowed_roots: list[Path] | None = None,
    ) -> Path:
        """Move an entry's files back to their original location.

        ``mode`` is "replace" (overwrite, backing up the existing file when
        asked) or "keep_both" (restore next to it under a new name like
        ``name (2)``). ``allowed_roots`` restricts where the original path
        may point (the library / Fleasion configs); anything else is
        refused. Returns the restored path; the trash entry disappears.
        """
        if allowed_roots:
            original = entry.original_path.resolve()
            if not any(
                root is not None and self._is_within(original, Path(root).resolve())
                for root in allowed_roots
            ):
                raise TrashError(t("trash_error.restore_refused"))

        if entry.kind == "file":
            dest_dir = entry.original_path.parent
            stem = entry.original_path.stem
        else:
            dest_dir = entry.original_path
            stem = None

        keep_both = mode == "keep_both" and self.destination_exists(entry)
        if keep_both and entry.kind == "folder":
            dest_dir = self._free_sibling(dest_dir)

        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise TrashError(
                t("trash_error.recreate_failed", dir=dest_dir, detail=exc.strerror or exc)
            ) from exc

        payload = self._payload_dir(entry)
        pairs: list[tuple[Path, Path]] = []
        for name in entry.files:
            src = payload / name
            if not src.is_file():
                continue
            if keep_both and entry.kind == "file":
                # « name (2).json » à côté de l'existant (jamais écrasé).
                if Path(name).stem == stem:
                    target_name = f"{stem} (2){Path(name).suffix}"
                elif name.startswith(stem):
                    target_name = name.replace(stem, f"{stem} (2)", 1)
                else:
                    target_name = name
                target = dest_dir / target_name
            else:
                target = dest_dir / name
            # Zip-slip style guard: every restored file stays inside the
            # recorded destination (which itself was validated above).
            if not self._is_within(target, dest_dir):
                raise TrashError(t("trash_error.invalid_path", name=name))
            target.parent.mkdir(parents=True, exist_ok=True)
            pairs.append((src, target))

        if not pairs:
            # Dossier vide : il suffit de le recréer à sa place.
            if entry.kind == "folder":
                try:
                    dest_dir.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    raise TrashError(
                        t("trash_error.recreate_failed", dir=dest_dir, detail=exc.strerror or exc)
                    ) from exc
                shutil.rmtree(entry.folder, ignore_errors=True)
                return dest_dir
            raise TrashError(t("trash_error.nothing_to_restore"))

        if backup_before_overwrite and backup_manager is not None and mode == "replace":
            existing = [t for _, t in pairs if t.exists()]
            if existing:
                try:
                    backup_manager.create_backup(existing)
                except (OSError, ValueError):
                    pass  # restore proceeds; the existing file is overwritten

        for src, target in pairs:
            try:
                shutil.copy2(src, target)
            except OSError as exc:
                raise TrashError(
                    t("trash_error.restore_failed", name=target.name, detail=exc.strerror or exc)
                ) from exc

        shutil.rmtree(entry.folder, ignore_errors=True)
        # The restored location: the original JSON for a file config, the
        # folder for a folder config, or the keep-both sibling.
        if keep_both and entry.kind == "file":
            return pairs[0][1]
        return entry.original_path if not keep_both else dest_dir

    def _free_sibling(self, dest_dir: Path) -> Path:
        """The next free destination for a « Garder les deux » restore."""
        candidate = Path(str(dest_dir) + " (2)")
        n = 3
        while candidate.exists():
            candidate = Path(f"{dest_dir} ({n})")
            n += 1
        return candidate

    # ------------------------------------------------------------------ #
    # Permanent deletion (only after explicit user confirmation)
    # ------------------------------------------------------------------ #
    def destroy(self, entry: TrashEntry) -> None:
        """Permanently delete an entry. The caller must have confirmed."""
        shutil.rmtree(entry.folder, ignore_errors=True)

    def empty(self) -> int:
        """Permanently delete every entry. Returns the number removed."""
        count = 0
        for entry in self.list_entries():
            self.destroy(entry)
            count += 1
        return count

    # ------------------------------------------------------------------ #
    # Listing
    # ------------------------------------------------------------------ #
    def list_entries(self) -> list[TrashEntry]:
        """All trash entries, most recent first."""
        entries: list[TrashEntry] = []
        if not self.root.is_dir():
            return entries
        for folder in sorted(self.root.iterdir(), reverse=True):
            if not folder.is_dir():
                continue
            meta = folder / TRASH_METADATA
            if not meta.is_file():
                meta = folder / LEGACY_METADATA  # entrées antérieures
            if not meta.is_file():
                continue
            try:
                data = json.loads(meta.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            created = self._parse_created(data, folder)
            entries.append(
                TrashEntry(
                    id=data.get("id", folder.name),
                    folder=folder,
                    name=data.get("name", data.get("original_name", folder.name)),
                    kind=data.get("kind", "file"),
                    original_path=Path(data.get("original_path", "")),
                    created=created,
                    files=list(data.get("files") or []),
                    category=data.get("category"),
                    weapon=data.get("weapon"),
                    size=int(data.get("size") or 0),
                    was_active=data.get("was_active"),
                )
            )
        return sorted(entries, key=lambda e: e.created, reverse=True)

    def _payload_dir(self, entry: TrashEntry) -> Path:
        payload = entry.folder / PAYLOAD_DIR
        return payload if payload.is_dir() else entry.folder

    # ------------------------------------------------------------------ #
    def _collect_sources(self, item: ConfigItem) -> list[Path]:
        """The item's library files plus its interface sidecars.

        Sidecars travel with the item so restoring it keeps the image and
        OBJ associations. The application caches (image_cache, obj_cache)
        are deliberately left untouched.
        """
        sources: list[Path] = []
        seen: set[str] = set()

        def add(path: Path) -> None:
            key = str(path)
            if path.is_file() and key not in seen:
                sources.append(path)
                seen.add(key)

        for p in item.files:
            add(p)
        if item.is_folder:
            for name in ("image.json", "obj.json"):
                add(item.path / name)
        else:
            for suffix in (".image.json", ".obj.json"):
                add(item.path.with_name(item.path.stem + suffix))
        return sorted(sources, key=lambda p: p.name.lower())

    # ------------------------------------------------------------------ #
    def _write_metadata(self, entry: TrashEntry) -> None:
        payload = {
            "version": TRASH_VERSION,
            "id": entry.id,
            "name": entry.name,
            "original_name": entry.name,
            "original_path": str(entry.original_path),
            "item_type": entry.item_type,
            "kind": entry.kind,
            "created": entry.created.strftime("%Y-%m-%dT%H:%M:%S"),
            "deleted_at": entry.created.strftime("%Y-%m-%dT%H:%M:%S"),
            "files": entry.files,
            "size": entry.size,
            "category": entry.category,
            "weapon": entry.weapon,
            "was_active": entry.was_active,
        }
        path = entry.folder / TRASH_METADATA
        tmp = entry.folder / (TRASH_METADATA + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    @staticmethod
    def _parse_created(data: dict, folder: Path) -> datetime:
        raw = data.get("created") or data.get("deleted_at")
        if raw:
            try:
                return datetime.strptime(raw, "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                pass
        return datetime.fromtimestamp(folder.stat().st_mtime)

    @staticmethod
    def _is_within(path: Path, base: Path) -> bool:
        try:
            path.resolve().relative_to(base)
            return True
        except ValueError:
            return False
