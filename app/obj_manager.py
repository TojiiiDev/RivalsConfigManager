"""OBJ manager: import local 3D models, remove associations.

The manager never touches the real configuration files (``.json`` /
``.obj``). It only writes the ``.obj.json`` sidecar and the application's
obj cache.

Supports multiple OBJ files per configuration: adding a new OBJ appends
it to the list, never replacing the existing ones.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import data_dir, obj_cache_dir
from .i18n import t
from .models import ConfigItem, Node
from .obj_metadata import (
    add_obj_metadata,
    associated_obj,
    associated_objs,
    delete_metadata,
    is_obj_metadata,
    load_metadata,
    remove_obj_metadata_at,
    replace_obj_metadata_at,
    save_metadata,
    stable_obj_id,
)

OBJ_EXTENSIONS = (".obj",)


class ObjError(Exception):
    """User-facing error with a clear message."""


def _friendly_os_error(exc: OSError, action: str) -> str:
    winerror = getattr(exc, "winerror", None)
    if winerror in (32, 33):
        return t("os_error.locked", action=action)
    if winerror == 5 or isinstance(exc, PermissionError):
        return t("os_error.permission", action=action)
    if getattr(exc, "errno", None) == 28:  # ENOSPC
        return t("os_error.no_space")
    return t("os_error.other", action=action, detail=exc.strerror or exc)


def validate_obj_file(path: Path) -> None:
    """Check that a file exists, is a ``.obj`` and is readable.

    The check stays deliberately light (no full 3D parser): existence,
    extension, non-empty and readable as text. This matches the project rule
    of not turning the manager into a 3D engine.
    """
    ext = path.suffix.lower()
    if ext not in OBJ_EXTENSIONS:
        raise ObjError(
            t("obj.unsupported_format", ext=ext or t("common.unknown"))
        )
    if not path.is_file():
        raise ObjError(t("obj.file_not_found", path=path))
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ObjError(
            _friendly_os_error(exc, t("obj.action_read"))
        ) from exc
    if not data.strip():
        raise ObjError(t("obj.empty", name=path.name))


class ObjManager:
    def __init__(self, cache_root: Path | None = None) -> None:
        self.cache_root = Path(cache_root) if cache_root else obj_cache_dir()
        self.cache_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    def cache_file_for(self, item: ConfigItem | Node, index: int = 0) -> Path:
        """Stable cache file name for an element's model at the given index.

        Each OBJ gets its own cache file (``<id>_0.obj``, ``<id>_1.obj``...).
        """
        return self.cache_root / f"{stable_obj_id(item)}_{index}.obj"

    def _next_index(self, item: ConfigItem | Node) -> int:
        """First free index for a new OBJ on this element."""
        meta = load_metadata(item)
        objs = meta.get("objs") if meta and isinstance(meta.get("objs"), list) else []
        return len(objs)

    def _relative(self, path: Path) -> str:
        """Store a path relative to the app data dir when possible."""
        try:
            rel = path.relative_to(data_dir())
        except ValueError:
            return str(path)
        return rel.as_posix()

    # ------------------------------------------------------------------ #
    def import_local(self, item: ConfigItem | Node, source: Path) -> Path:
        """Copy a local obj into the cache and APPEND it to the sidecar.

        Adding a new OBJ never replaces the existing ones — each OBJ gets
        its own cache file. Returns the cache file path.

        Backward-compatible: calling this on an item that had a v1 single
        OBJ will add a second OBJ without losing the first (auto-migrated).
        """
        source = Path(source)
        validate_obj_file(source)

        index = self._next_index(item)
        dest = self.cache_file_for(item, index)
        try:
            shutil.copy2(source, dest)
        except OSError as exc:
            raise ObjError(
                _friendly_os_error(exc, t("obj.action_copy"))
            ) from exc

        add_obj_metadata(item, dest, source)
        return dest

    # ------------------------------------------------------------------ #
    def remove(self, item: ConfigItem | Node) -> None:
        """Remove ALL obj associations for this element.

        Deletes the sidecar and every cached model that belongs to this
        element. The real ``.json`` / ``.obj`` files are never touched.
        """
        cached_list = associated_objs(item)
        for cached in cached_list:
            if cached.is_relative_to(self.cache_root):
                try:
                    cached.unlink()
                except OSError:
                    pass
        delete_metadata(item)

    # ------------------------------------------------------------------ #
    def remove_one(self, item: ConfigItem | Node, index: int) -> bool:
        """Remove a single OBJ at the given index. Other OBJs are kept.

        Returns True when the sidecar was updated.
        """
        return remove_obj_metadata_at(item, index)

    def replace_one(self, item: ConfigItem | Node, index: int, source: Path) -> Path:
        """Replace one OBJ at the given index. Other OBJs are kept."""
        source = Path(source)
        validate_obj_file(source)
        dest = self.cache_file_for(item, index)
        try:
            shutil.copy2(source, dest)
        except OSError as exc:
            raise ObjError(
                _friendly_os_error(exc, t("obj.action_copy"))
            ) from exc
        replace_obj_metadata_at(item, index, dest, source)
        return dest

    def count(self, item: ConfigItem | Node) -> int:
        """Number of OBJs associated with this element."""
        return len(associated_objs(item))

    # Backward compat delegator (v1) ------------------------------------- #
    def cache_file_for_legacy(self, item: ConfigItem | Node) -> Path:
        """Stable cache file name (index 0, backward compat)."""
        return self.cache_root / f"{stable_obj_id(item)}.obj"

    # ------------------------------------------------------------------ #
    @staticmethod
    def is_obj_metadata(path: Path) -> bool:
        """Delegate so the scanner can exclude obj sidecars uniformly."""
        return is_obj_metadata(path)
