"""Check for library images that are not yet published in ``manifest.json``.

Run this **before every release** (or commit that changes assets). It scans the
developer's library for image sidecars and folder previews, then compares them
against the current ``manifest.json``. Anything missing from the manifest is
reported — these images would NOT be visible on a fresh installation.

Usage (from the project root)::

    python tools/check_unpublished_assets.py
    python tools/check_unpublished_assets.py --library "C:\\...\\Rivals configs"

Exit codes:

* 0 — everything is published (or no library found = cannot check).
* 1 — unpublished images found (must run ``sync_assets_from_library.py``).
* 2 — library not found, check skipped.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def project_root() -> Path:
    return ROOT


def slug(name: str) -> str:
    """Same normalisation as ``app.assets.cache.slug``."""
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in name.strip().casefold())
    return "_".join(part for part in cleaned.split("_") if part)


def _read_settings() -> dict | None:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return None
    path = Path(appdata) / "RivalsConfigManager" / "settings.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def _collect_sidecars(library: Path) -> list[tuple[Path, tuple[str, ...]]]:
    found: list[tuple[Path, tuple[str, ...]]] = []
    for p in sorted(library.rglob("*")):
        if p.is_file() and (p.name == "image.json" or p.name.endswith(".image.json")):
            found.append((p, p.relative_to(library).parts))
    return found


PREVIEW_STEMS = {
    "preview", "thumbnail", "thumb", "cover", "image", "icon",
    "apercu", "aper\u00e7u", "screenshot",
}
PREVIEW_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


def _collect_folder_previews(library: Path) -> list[tuple[Path, tuple[str, ...]]]:
    """``preview.*`` files found directly inside library folders."""
    found: list[tuple[Path, tuple[str, ...]]] = []
    for p in sorted(library.rglob("*")):
        if (
            p.is_file()
            and p.suffix.lower() in PREVIEW_EXTS
            and p.stem.lower() in PREVIEW_STEMS
            and not (p.parent / "image.json").is_file()
        ):
            found.append((p, p.relative_to(library).parts))
    return found


def _item_name(sidecar: Path) -> str:
    if sidecar.name == "image.json":
        return sidecar.parent.name
    return sidecar.name[: -len(".image.json")]


def chain_key(rel_parts: tuple[str, ...], sidecar: Path, name: str) -> str:
    """The stable key (same as ``sync_assets_from_library``)."""
    folders = rel_parts[:-1]
    if sidecar.name == "image.json":
        chain = list(folders)
    else:
        chain = [*folders, name]
    parts = [slug(c) for c in chain if slug(c)]
    return "/".join(parts)


def _safe_print(text: str, **kwargs) -> None:
    """Print to stdout, replacing non-ASCII chars when the console can't
    handle them (common on Windows CP1252 terminals)."""
    try:
        print(text, **kwargs)
    except UnicodeEncodeError:
        ascii_text = text.encode("ascii", errors="replace").decode("ascii")
        print(ascii_text, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=None)
    parser.add_argument(
        "--json", action="store_true", help="sortie JSON (machine-readable)"
    )
    args = parser.parse_args()

    root = project_root()
    manifest_path = root / "manifest.json"

    if not manifest_path.is_file():
        print("X manifest.json introuvable -- impossible de verifier.",
              file=sys.stderr)
        return 2

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"X manifest.json illisible ({exc})", file=sys.stderr)
        return 2

    manifest_assets: dict = (
        manifest.get("assets", {}) if isinstance(manifest, dict) else {}
    )
    published_keys = set(manifest_assets.keys())

    # Resolve library.
    library = args.library
    if library is None:
        settings = _read_settings()
        raw = settings.get("library_dir") if settings else None
        library = Path(raw) if raw else None

    if library is None or not library.is_dir():
        if args.json:
            print(json.dumps({"status": "skipped", "reason": "library_not_found"}))
        else:
            _safe_print(
                "Bibliotheque introuvable -- verification ignoree."
            )
            _safe_print("  Passez --library PATH pour pointer vers la bibliotheque.")
        return 2

    # Collect all library image sources and derive their keys.
    unpublished: list[dict] = []
    library_keys: set[str] = set()

    for sidecar, rel_parts in _collect_sidecars(library):
        name = _item_name(sidecar)
        if not name.strip():
            continue
        key = chain_key(rel_parts, sidecar, name)
        if not key:
            continue
        library_keys.add(key)
        if key not in published_keys:
            unpublished.append({
                "key": key,
                "source": str(sidecar.relative_to(library)),
                "type": "sidecar",
            })

    for preview, rel_parts in _collect_folder_previews(library):
        folders = rel_parts[:-1]
        key = "/".join(slug(c) for c in folders if slug(c))
        if not key:
            continue
        library_keys.add(key)
        if key not in published_keys:
            unpublished.append({
                "key": key,
                "source": str(preview.relative_to(library)),
                "type": "preview_file",
            })

    # Stale check: items in manifest that no longer exist in the library.
    stale = [k for k in published_keys if k not in library_keys]

    if args.json:
        print(json.dumps({
            "status": "unpublished" if unpublished else "ok",
            "published": len(published_keys),
            "library_images": len(library_keys),
            "unpublished": unpublished,
            "stale": stale,
        }, indent=2))
    else:
        _safe_print(f"Manifest     : {len(published_keys)} assets publies")
        _safe_print(f"Bibliotheque : {len(library_keys)} images trouvees")
        _safe_print(f"Version assets : {manifest.get('assets_version', 'N/A')}")
        print()

        if unpublished:
            _safe_print(f">> {len(unpublished)} image(s) NON PUBLIEE(S) :")
            _safe_print("   Ces images existent dans la bibliotheque mais pas dans le manifest.")
            _safe_print("   Elles ne seront PAS visibles sur une installation propre.")
            print()
            for item in unpublished:
                _safe_print(f"   - [{item['type']}] {item['key']}")
                _safe_print(f"     source : {item['source']}")
            print()
            _safe_print("   Action : python tools/sync_assets_from_library.py")
            _safe_print("            git add assets/ manifest.json && git commit && git push")
        else:
            _safe_print("OK Toutes les images de la bibliotheque sont publiees.")

        if stale:
            print()
            _safe_print(f"!  {len(stale)} entree(s) obsolete(s) dans le manifest :")
            for k in sorted(stale)[:10]:
                _safe_print(f"   - {k}")
            if len(stale) > 10:
                _safe_print(f"   ... et {len(stale) - 10} de plus")

        if unpublished:
            print()
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())