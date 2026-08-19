"""Local asset cache — where downloaded assets live and how they are found.

Assets are stored under the per-user data folder, never next to the ``.exe``
and never in the working directory:

    %APPDATA%\\RivalsConfigManager\\
        assets\\            <- asset files (mirroring the repository layout)
        asset_manifest.json <- the last successfully synced manifest

The cache is always consulted first (fast, offline): a card can display an
asset image immediately when it is already downloaded, without any network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .manifest import AssetManifest, ManifestError, parse_manifest, loads
from .security import relative_cache_path

#: File name of the local manifest inside the app data folder.
LOCAL_MANIFEST_NAME = "asset_manifest.json"


def slug(name: str) -> str:
    """A normalised identity used to match card names to asset keys.

    ``"Assault Rifle"`` and ``"assault_rifle"`` both become
    ``"assault_rifle"``, so a manifest key and a library folder name can be
    compared without case/separator sensitivity.
    """
    cleaned = "".join(
        ch if ch.isalnum() else "_" for ch in name.strip().casefold()
    )
    return "_".join(part for part in cleaned.split("_") if part)


def assets_cache_dir() -> Path:
    """Return (and create) the directory holding downloaded assets."""
    from app.config import data_dir

    d = data_dir() / "assets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def local_manifest_file() -> Path:
    """Path of the persisted local manifest."""
    from app.config import data_dir

    return data_dir() / LOCAL_MANIFEST_NAME


@dataclass
class LocalCacheState:
    """What the local cache currently holds."""

    manifest: AssetManifest | None  # None = never synced yet
    files: dict[str, Path]          # key -> cached file path (existing files)


class LocalAssetCache:
    """Read/write the per-user asset cache and its manifest."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root is not None else assets_cache_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self._manifest_path = (
            local_manifest_file() if root is None else Path(root).parent / LOCAL_MANIFEST_NAME
        )

    # ------------------------------------------------------------------ #
    def file_for(self, path: str) -> Path:
        """Absolute cache path for a manifest path (e.g. ``assets/weapons/x.png``)."""
        return self.root / relative_cache_path(path)

    def has_file(self, path: str) -> bool:
        """True when the asset file exists in the cache."""
        return self.file_for(path).is_file()

    # ------------------------------------------------------------------ #
    def load_state(self) -> LocalCacheState:
        """The persisted manifest + the asset files actually on disk.

        Never raises: a missing/corrupt local manifest is reported as
        ``manifest=None`` and the cache keeps whatever files exist.
        """
        manifest: AssetManifest | None = None
        if self._manifest_path.is_file():
            try:
                manifest = loads(self._manifest_path.read_text(encoding="utf-8-sig"))
            except (ManifestError, OSError, UnicodeDecodeError):
                manifest = None

        files: dict[str, Path] = {}
        if manifest is not None:
            for key, entry in manifest.assets.items():
                path = self.file_for(entry.path)
                if path.is_file():
                    files[key] = path
        return LocalCacheState(manifest=manifest, files=files)

    # ------------------------------------------------------------------ #
    def write_manifest(self, manifest: AssetManifest) -> None:
        """Persist the local manifest atomically (after a successful sync)."""
        payload = {
            "schema_version": manifest.schema_version,
            "assets_version": manifest.assets_version,
            "assets": {
                key: {
                    "path": entry.path,
                    "version": entry.version,
                    **({"size": entry.size} if entry.size is not None else {}),
                    **({"sha256": entry.sha256} if entry.sha256 else {}),
                }
                for key, entry in manifest.assets.items()
            },
        }
        tmp = self._manifest_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._manifest_path)

    def clear_manifest(self) -> None:
        """Remove the local manifest (used when the remote is unreachable in
        a way that should not pretend assets are still synced)."""
        try:
            self._manifest_path.unlink()
        except OSError:
            pass

    # ------------------------------------------------------------------ #
    # Resolution by name (best-effort, offline)
    # ------------------------------------------------------------------ #
    def find_image(self, *names: str) -> Path | None:
        """The cached image whose key matches any of ``names``, or ``None``.

        Purely local (reads the persisted manifest + existing files); used as
        a last-resort image for cards that have no library preview or sidecar.
        """
        state = self.load_state()
        if state.manifest is None:
            return None
        wanted = {slug(n) for n in names if n}
        for key, entry in state.manifest.assets.items():
            if slug(key) in wanted:
                path = self.file_for(entry.path)
                if path.is_file():
                    return path
        return None

    def cached_path_for_key(self, key: str) -> Path | None:
        """The cached file for an exact asset key, or ``None``."""
        state = self.load_state()
        if state.manifest is None:
            return None
        entry = state.manifest.entry(key)
        if entry is None:
            return None
        path = self.file_for(entry.path)
        return path if path.is_file() else None
