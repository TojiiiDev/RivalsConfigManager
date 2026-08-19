"""OBJ manager: import local 3D models, remove associations.

The manager never touches the real configuration files (``.json`` /
``.obj``). It only writes the ``.obj.json`` sidecar and the application's
obj cache.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from .config import data_dir, obj_cache_dir
from .i18n import t
from .models import ConfigItem, Node
from .obj_metadata import (
    associated_obj,
    delete_metadata,
    is_obj_metadata,
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
    def cache_file_for(self, item: ConfigItem | Node) -> Path:
        """Stable cache file name for an element's model."""
        return self.cache_root / f"{stable_obj_id(item)}.obj"

    def _relative(self, path: Path) -> str:
        """Store a path relative to the app data dir when possible."""
        try:
            rel = path.relative_to(data_dir())
        except ValueError:
            return str(path)
        return rel.as_posix()

    # ------------------------------------------------------------------ #
    def import_local(self, item: ConfigItem | Node, source: Path) -> Path:
        """Copy a local obj into the cache and write the sidecar.

        Returns the cache file path. Raises :class:`ObjError` with a clear
        message on any problem.
        """
        source = Path(source)
        validate_obj_file(source)

        dest = self.cache_file_for(item)
        try:
            shutil.copy2(source, dest)
        except OSError as exc:
            raise ObjError(
                _friendly_os_error(exc, t("obj.action_copy"))
            ) from exc

        save_metadata(
            item,
            {
                "type": "local",
                "source": str(source),
                "local_path": self._relative(dest),
                "file_name": source.name,
            },
        )
        return dest

    # ------------------------------------------------------------------ #
    def remove(self, item: ConfigItem | Node) -> None:
        """Remove the obj association.

        Deletes the sidecar and the cached model (only if it belongs to this
        element). The real ``.json`` / ``.obj`` files are never touched.
        """
        cached = associated_obj(item)
        if cached is not None and cached.is_relative_to(self.cache_root):
            try:
                cached.unlink()
            except OSError:
                pass
        delete_metadata(item)

    # ------------------------------------------------------------------ #
    @staticmethod
    def is_obj_metadata(path: Path) -> bool:
        """Delegate so the scanner can exclude obj sidecars uniformly."""
        return is_obj_metadata(path)
