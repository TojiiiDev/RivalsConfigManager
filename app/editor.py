"""Editor Mode integration logic — pure Python, no Qt dependency.

The Editor Mode is the **creator** side of the shared-asset system. It turns
a locally-chosen image into a real project resource:

1. the image is copied into the application's per-user cache and associated
   to the element through the existing ``.image.json`` sidecar (so the card
   updates immediately and the source PC file is never needed again);
2. the image is copied into the repository ``assets/`` tree and registered
   in ``manifest.json`` under the element's stable slug-chain key — the very
   same system the application already uses to deliver previews to every
   user (see ``app/assets/`` and ``tools/sync_assets_from_library.py``).

The identifier is the slug chain of the element's path **relative to the
library root** (e.g. ``rivals_skins/melee/battle_axe/nordicaxe``), never the
displayed name and never an absolute path: it is portable across machines
and survives name / language / layout changes.
"""

from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .assets.cache import slug
from .i18n import t
from .image_manager import ImageError, ImageManager
from .models import ConfigItem, Node

SCHEMA_VERSION = 1

#: Any element that can be displayed as a card and given a preview.
EditorTarget = Node | ConfigItem


def default_project_root() -> Path | None:
    """The source-tree project root (where ``assets/`` and ``manifest.json``
    live), or ``None`` in a frozen build (the bundled resources cannot be
    edited from inside the ``.exe``)."""
    if getattr(sys, "frozen", False):
        return None
    return Path(__file__).resolve().parent.parent


def _resolve(path: Path) -> Path:
    """Resolve a path defensively (never raises on a broken path)."""
    try:
        return path.resolve()
    except OSError:
        return Path(path)


def asset_key_for(item: EditorTarget, library_root: Node) -> str:
    """The stable manifest key: the slug chain of ``item``'s path relative to
    the library root, root-first and joined with forward slashes.

    For a folder/category node the last component is the folder name; for a
    single-file configuration it is the file stem (``item.name``), so the key
    matches what the application reconstructs from a scanned card.
    """
    root_path = _resolve(library_root.path)
    parts = [slug(item.name)]
    current = item.path.parent
    for _ in range(64):  # hard safety cap — never an infinite walk
        if current is None:
            break
        parent = current.parent
        if _resolve(current) == root_path:
            break
        if current.name:
            parts.append(slug(current.name))
        if parent == current:
            break  # filesystem root
        current = parent
    parts = [p for p in reversed(parts) if p]
    return "/".join(parts)


# ---------------------------------------------------------------------- #
# Manifest helpers (the repository ``manifest.json``)
# ---------------------------------------------------------------------- #
def _default_manifest() -> dict:
    return {"schema_version": SCHEMA_VERSION, "assets_version": "", "assets": {}}


def load_project_manifest(project_root: Path) -> dict:
    """Read the repository manifest (never raises; a missing/corrupt file
    yields an empty manifest that will be regenerated)."""
    path = project_root / "manifest.json"
    if not path.is_file():
        return _default_manifest()
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return _default_manifest()
    if not isinstance(data, dict):
        return _default_manifest()
    data.setdefault("schema_version", SCHEMA_VERSION)
    data.setdefault("assets_version", "")
    assets = data.get("assets")
    if not isinstance(assets, dict):
        assets = {}
        data["assets"] = assets
    return data


def _write_project_manifest(project_root: Path, manifest: dict) -> None:
    """Write the repository manifest atomically."""
    path = project_root / "manifest.json"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(manifest, indent=4, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    tmp.replace(path)


def _bump_assets_version(old: str | None) -> str:
    """Today-based asset release version (same convention as the sync tool)."""
    today = date.today().strftime("%Y.%m.%d")
    if old and old.startswith(today + "."):
        try:
            return f"{today}.{int(old.rsplit('.', 1)[1]) + 1}"
        except (ValueError, IndexError):
            pass
    return f"{today}.1"


# ---------------------------------------------------------------------- #
# Editor manager
# ---------------------------------------------------------------------- #
@dataclass
class EditorResult:
    """Outcome of an editor integration/removal."""

    ok: bool = False
    name: str = ""
    #: The local (sidecar) preview path — set once the image is associated.
    preview: Path | None = None
    #: The stable manifest key (slug chain).
    asset_key: str | None = None
    #: The project resource file (``None`` when not published).
    asset_path: Path | None = None
    #: True when the image was written into ``assets/`` + ``manifest.json``.
    project_integrated: bool = False
    #: Asset version recorded in the manifest (``None`` when not published).
    version: int | None = None
    #: A user-facing error message (``None`` on success).
    error: str | None = None


class EditorManager:
    """Integrate / remove previews as project resources.

    ``library_root`` is the scanned library root :class:`Node` (used to
    derive stable keys); ``project_root`` is the repository root (defaults to
    the source-tree root, ``None`` when frozen). Both are injectable so the
    logic is fully testable without touching the real repository.
    """

    def __init__(
        self,
        library_root: Node | None = None,
        project_root: Path | None = None,
        image_manager: ImageManager | None = None,
    ) -> None:
        self.library_root = library_root
        self.project_root = (
            project_root if project_root is not None else default_project_root()
        )
        self.image_manager = image_manager or ImageManager()

    # ------------------------------------------------------------------ #
    def _publishable(self) -> bool:
        return bool(self.project_root) and (self.project_root / "assets").is_dir()

    # ------------------------------------------------------------------ #
    def integrate(self, item: EditorTarget, source: Path) -> EditorResult:
        """Copy ``source`` into the app's cache + sidecar, then publish it
        into the repository ``assets/`` + ``manifest.json``.

        The sidecar association always succeeds first (so the card updates
        even when the project cannot be published, e.g. a frozen build). The
        original PC file is never stored as the preview location.
        """
        result = EditorResult(name=item.name)
        try:
            cache_path = self.image_manager.import_local(
                item, Path(source), record_source=False
            )
        except ImageError as exc:
            result.error = str(exc)
            return result
        result.preview = cache_path

        if self.library_root is None:
            result.ok = True
            result.error = t("editor.no_library_root")
            return result

        key = asset_key_for(item, self.library_root)
        result.asset_key = key
        if not key:
            result.ok = True
            result.error = t("editor.empty_key")
            return result

        if not self._publishable():
            # The local association is done; project publishing is unavailable.
            result.ok = True
            result.error = t("editor.project_unavailable")
            return result

        try:
            asset_path, version = self._publish(key, cache_path)
        except OSError as exc:
            # The local association is already done; only the project publish
            # failed (disk full / permission). Report it without losing the
            # association.
            result.ok = True
            result.error = str(exc)
            return result

        result.project_integrated = True
        result.asset_path = asset_path
        result.version = version
        result.ok = True
        return result

    # ------------------------------------------------------------------ #
    def _publish(self, key: str, source: Path) -> tuple[Path, int]:
        """Copy ``source`` into ``assets/<key>.<ext>`` and update the
        manifest (new entry = version 1; changed content = version + 1).
        Replacing with a different extension removes the old file, so no
        ``AK.png`` / ``AK_1.png`` duplicates ever accumulate."""
        data = source.read_bytes()
        ext = source.suffix.lower().lstrip(".") or "png"
        rel_target = f"assets/{key}.{ext}"
        target = self.project_root / "assets" / f"{key}.{ext}"
        digest = hashlib.sha256(data).hexdigest()

        manifest = load_project_manifest(self.project_root)
        assets = manifest["assets"]
        old = assets.get(key) if isinstance(assets.get(key), dict) else None
        old_digest = old.get("sha256") if old else None
        old_version = old.get("version") if old else None
        old_path = old.get("path") if old else None

        version = 1
        if isinstance(old_version, int) and old_version >= 1:
            version = old_version + 1 if old_digest != digest else old_version

        changed = old_digest != digest or old_path != rel_target

        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(target)

        # Extension changed -> drop the previous resource file cleanly.
        if old_path and old_path != rel_target:
            old_file = self.project_root / old_path
            if old_file.is_file():
                try:
                    old_file.unlink()
                except OSError:
                    pass

        assets[key] = {
            "path": rel_target,
            "version": version,
            "size": len(data),
            "sha256": digest,
        }

        if changed or not manifest.get("assets_version"):
            manifest["assets_version"] = _bump_assets_version(
                manifest.get("assets_version") or None
            )

        _write_project_manifest(self.project_root, manifest)
        return target, version

    # ------------------------------------------------------------------ #
    def remove(self, item: EditorTarget) -> EditorResult:
        """Remove the image association: the sidecar + cached image, and (when
        published) the repository asset + its manifest entry."""
        result = EditorResult(name=item.name)
        self.image_manager.remove(item)
        result.preview = None

        if self.library_root is None:
            result.ok = True
            return result
        key = asset_key_for(item, self.library_root)
        result.asset_key = key
        if not key or not self._publishable():
            result.ok = True
            return result

        manifest = load_project_manifest(self.project_root)
        assets = manifest["assets"]
        old = assets.pop(key, None)
        removed_file = False
        if isinstance(old, dict) and old.get("path"):
            old_file = self.project_root / old["path"]
            if old_file.is_file():
                try:
                    old_file.unlink()
                    removed_file = True
                except OSError:
                    pass

        if isinstance(old, dict) or removed_file:
            manifest["assets_version"] = _bump_assets_version(
                manifest.get("assets_version") or None
            )
            _write_project_manifest(self.project_root, manifest)

        result.ok = True
        return result
