"""Image manager: import local images, finalize URL downloads, removal.

The manager never touches the real configuration files (``.json`` / ``.obj``).
It only writes the ``.image.json`` sidecar and the application's image cache.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtGui import QImage

from .config import data_dir, image_cache_dir
from .i18n import t
from .image_metadata import CardTarget, delete_metadata, local_image_path, save_metadata, stable_id
from .models import ConfigItem, Node

#: Image formats accepted by the import dialog.
ALLOWED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".bmp")


class ImageError(Exception):
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


def validate_image_file(path: Path) -> None:
    """Check that a file exists, has an accepted extension and decodes."""
    ext = path.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ImageError(
            t("image_error.unsupported_format", ext=ext or t("common.unknown"))
        )
    if not path.is_file():
        raise ImageError(t("common.file_not_found", name=path))
    if QImage(str(path)).isNull():
        raise ImageError(t("image_error.corrupt", name=path.name))


class ImageManager:
    def __init__(self, cache_root: Path | None = None) -> None:
        self.cache_root = Path(cache_root) if cache_root else image_cache_dir()
        self.cache_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    def cache_file_for(self, item: CardTarget, ext: str) -> Path:
        """Stable cache file name for a configuration or a folder."""
        return self.cache_root / f"{stable_id(item)}{ext.lower()}"

    def _relative(self, path: Path) -> str:
        """Store a path relative to the app data dir when possible, so the
        metadata stays portable; fall back to the absolute path for custom
        cache roots (e.g. in tests)."""
        try:
            rel = path.relative_to(data_dir())
        except ValueError:
            return str(path)
        # Store with forward slashes (portable, matches the documented format).
        return rel.as_posix()

    # ------------------------------------------------------------------ #
    def import_local(
        self, item: CardTarget, source: Path, record_source: bool = True
    ) -> Path:
        """Copy a local image into the cache and write the sidecar.

        Returns the cache file path. Raises :class:`ImageError` with a clear
        message on any problem.

        ``record_source`` controls whether the original PC path is kept in
        the sidecar's ``source`` field. The Editor Mode passes ``False`` so
        the association never stores a personal path (the preview is the
        cached copy, keyed by the element's stable id — ``local_path``).
        """
        source = Path(source)
        validate_image_file(source)

        dest = self.cache_file_for(item, source.suffix)
        try:
            shutil.copy2(source, dest)
        except OSError as exc:
            raise ImageError(
                _friendly_os_error(exc, t("image_error.action_copy"))
            ) from exc

        metadata: dict = {"type": "local", "local_path": self._relative(dest)}
        if record_source:
            metadata["source"] = str(source)
        save_metadata(item, metadata)
        return dest

    # ------------------------------------------------------------------ #
    def save_downloaded(self, item: CardTarget, url: str, file_path: Path) -> None:
        """Write the sidecar for an already-downloaded, validated image."""
        save_metadata(
            item,
            {
                "type": "url",
                "source": url,
                "local_path": self._relative(Path(file_path)),
            },
        )

    # ------------------------------------------------------------------ #
    def remove(self, item: CardTarget) -> None:
        """Remove the image association.

        Deletes the sidecar and the cached image file (only if it belongs to
        this configuration). The real ``.json`` / ``.obj`` files are never
        touched.
        """
        cached = local_image_path(item)
        if cached is not None and cached.is_relative_to(self.cache_root):
            try:
                cached.unlink()
            except OSError:
                pass
        delete_metadata(item)
