"""Import the library's images into ``assets/`` and regenerate ``manifest.json``.

This is the **publisher** side of the shared-asset system. It reads the local
Fleasion library (the ``.image.json`` / ``image.json`` sidecars next to the
configurations) plus the developer's image cache, copies every image into the
repository ``assets/`` tree, and writes a versioned ``manifest.json``.

The result is what gets pushed to GitHub so every user's app can fetch the
images without receiving a new ``.exe``.

Usage (from the project root)::

    python tools/sync_assets_from_library.py
    python tools/sync_assets_from_library.py --library "C:\\...\\Rivals configs"
    python tools/sync_assets_from_library.py --library PATH --data-dir PATH

Layout
------

The repository layout **mirrors the library** so the manifest key is always
identical to the storage path (minus the ``assets/`` prefix and extension):

    assets/charms/nemesis_charm.webp
    assets/rivals_skins/melee/battle_axe/nordicaxe.webp

and the matching manifest entry:

    "charms/nemesis_charm": {"path": "assets/charms/nemesis_charm.webp", ...}

The key is the slug chain of the item's path **relative to the library root**,
which is what the application reconstructs from a scanned card (item name +
ancestor folders). Using the full chain — not just the name — means two
items that differ only by case ("Hand gun" folder vs "hand gun" skin) never
collide.

Behaviour
---------

* library path from ``--library``, else the app settings
  (``%APPDATA%\\RivalsConfigManager\\settings.json``);
* image cache from the app data dir (``--data-dir``), else
  ``%APPDATA%\\RivalsConfigManager`` (the sidecar ``local_path`` is relative to it);
* an image whose content changed (sha256) gets its version bumped by 1; a new
  image starts at version 1; an image whose sidecar disappeared is removed from
  the manifest;
* rewrites ``manifest.json`` so it describes **exactly** what is in ``assets/``.

The tool is idempotent and never deletes the developer's image cache (it only
copies from it).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from datetime import date
from pathlib import Path

SCHEMA_VERSION = 1


def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def slug(name: str) -> str:
    """Filesystem-safe slug (same normalisation as ``app.assets.cache.slug``)."""
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in name.strip().casefold())
    return "_".join(part for part in cleaned.split("_") if part)


def detect_ext(data: bytes) -> str | None:
    """Real image extension from magic bytes (never trusts the file name).

    ``detect_image_ext`` returns a leading-dot value (``".png"``); we strip it
    so the generated file name has a single dot.
    """
    from app.image_downloader import detect_image_ext

    ext = detect_image_ext(data)
    return ext.lstrip(".") if ext else None


def _item_name(sidecar: Path) -> str:
    if sidecar.name == "image.json":
        return sidecar.parent.name
    return sidecar.name[: -len(".image.json")]


def chain_key(rel_parts: tuple[str, ...], sidecar: Path, name: str) -> str:
    """The stable key: slug chain of the path relative to the library root.

    For a folder image (``image.json``) the chain is the folder path; for a
    configuration (``<name>.image.json``) it is the folder path + the name.
    """
    folders = rel_parts[:-1]  # drop the sidecar file name itself
    if sidecar.name == "image.json":
        chain = list(folders)
    else:
        chain = [*folders, name]
    parts = [slug(c) for c in chain if slug(c)]
    return "/".join(parts)


def _bump_assets_version(old: str | None) -> str:
    today = date.today().strftime("%Y.%m.%d")
    if old and old.startswith(today + "."):
        try:
            return f"{today}.{int(old.rsplit('.', 1)[1]) + 1}"
        except (ValueError, IndexError):
            pass
    return f"{today}.1"


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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=None)
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="dossier de données de l'app (défaut : %%APPDATA%%/RivalsConfigManager)",
    )
    args = parser.parse_args()

    root = project_root()
    # Make ``app`` importable regardless of the working directory.
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    assets_dir = root / "assets"
    manifest_path = root / "manifest.json"

    # Resolve the library path.
    library = args.library
    if library is None:
        settings = _read_settings()
        raw = settings.get("library_dir") if settings else None
        library = Path(raw) if raw else None
    if library is None or not library.is_dir():
        print("X Bibliothèque introuvable. Passez --library PATH.", file=sys.stderr)
        return 2

    # Resolve the app data dir (the sidecar ``local_path`` is relative to it,
    # e.g. ``image_cache/<id>.png``).
    data_dir = args.data_dir
    if data_dir is None:
        appdata = os.environ.get("APPDATA")
        data_dir = Path(appdata) / "RivalsConfigManager" if appdata else None
    if data_dir is None or not data_dir.is_dir():
        print("X Dossier de données introuvable. Passez --data-dir PATH.", file=sys.stderr)
        return 2

    # Previous manifest (to preserve per-asset versions and detect removals).
    old_manifest: dict = {"schema_version": SCHEMA_VERSION, "assets_version": "", "assets": {}}
    if manifest_path.is_file():
        try:
            old_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("! manifest.json illisible, il sera régénéré.", file=sys.stderr)

    old_assets = old_manifest.get("assets", {}) if isinstance(old_manifest, dict) else {}

    entries: dict[str, dict] = {}
    seen_keys: dict[str, str] = {}   # key -> sidecar path (duplicate detection)
    errors: list[str] = []
    top_counts: Counter[str] = Counter()
    changed = 0

    for sidecar, rel_parts in _collect_sidecars(library):
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{sidecar.name} : sidecar illisible ({exc})")
            continue

        local_path = meta.get("local_path") if isinstance(meta, dict) else None
        if not isinstance(local_path, str) or not local_path:
            errors.append(f"{sidecar.name} : local_path manquant")
            continue

        src = data_dir / Path(local_path)
        if not src.is_file():
            errors.append(f"{sidecar.name} : image absente du cache ({local_path})")
            continue
        data = src.read_bytes()

        ext = detect_ext(data)
        if ext is None:
            errors.append(f"{sidecar.name} : image invalide ({local_path})")
            continue

        name = _item_name(sidecar)
        if not name.strip():
            errors.append(f"{sidecar} : nom d'élément vide")
            continue

        key = chain_key(rel_parts, sidecar, name)
        if not key:
            errors.append(f"{sidecar} : clé vide")
            continue
        if key in seen_keys:
            errors.append(f"{key} : clé dupliquée ({sidecar} vs {seen_keys[key]})")
            continue
        seen_keys[key] = str(sidecar)

        rel_target = f"assets/{key}.{ext}"
        target = assets_dir / f"{key}.{ext}"

        digest = hashlib.sha256(data).hexdigest()
        old_entry = old_assets.get(key) if isinstance(old_assets, dict) else None
        old_digest = old_entry.get("sha256") if isinstance(old_entry, dict) else None
        old_version = old_entry.get("version") if isinstance(old_entry, dict) else None
        version = (
            old_version + 1
            if isinstance(old_version, int) and old_digest != digest
            else (old_version if isinstance(old_version, int) else 1)
        )
        if old_digest != digest or old_entry.get("path") != rel_target:
            changed += 1

        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_bytes() != data:
            target.write_bytes(data)

        entries[key] = {
            "path": rel_target,
            "version": version,
            "size": len(data),
            "sha256": digest,
        }
        top_counts[key.split("/")[0]] += 1

    if errors:
        print("X Erreurs rencontrées - manifest NON modifié :", file=sys.stderr)
        for e in errors:
            print(f"   - {e}", file=sys.stderr)
        return 1

    # Remove stale generated files (a deleted sidecar must not leave its old
    # asset in the repository). Reserved files (icon, README) are kept.
    reserved = {"icon.png", "icon.ico", "README.md"}

    def _rel_to_assets(path: str) -> str:
        return path[len("assets/") :] if path.startswith("assets/") else path

    keep_paths = {_rel_to_assets(e["path"]) for e in entries.values()}
    cleaned_files = 0
    for p in sorted(assets_dir.rglob("*"), reverse=True):
        if p.is_file():
            rel = p.relative_to(assets_dir).as_posix()
            if rel not in keep_paths and p.name not in reserved:
                try:
                    p.unlink()
                    cleaned_files += 1
                except OSError:
                    pass
        elif p.is_dir() and not any(p.iterdir()):
            try:
                p.rmdir()
            except OSError:
                pass
    if cleaned_files:
        changed += 1

    # Remove stale assets (sidecar deleted from the library) so clients drop them.
    removed = [k for k in old_assets if k not in entries]
    if removed:
        changed += 1

    old_version = old_manifest.get("assets_version") if isinstance(old_manifest, dict) else None
    # Only bump the release version when something actually changed; an
    # idempotent run must not create a spurious new release.
    new_version = (
        _bump_assets_version(old_version)
        if (changed or removed)
        else (old_version or _bump_assets_version(None))
    )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "assets_version": new_version,
        "assets": entries,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=4, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    total_bytes = sum(e["size"] for e in entries.values())
    print(f"OK {len(entries)} assets intégrés ({total_bytes / 1024 / 1024:.2f} Mo)")
    for top, n in sorted(top_counts.items()):
        print(f"   - {top}: {n}")
    print(f"   version des assets : {new_version}")
    if changed:
        print(f"   {changed} entrée(s) nouvelle(s)/modifiée(s)")
    if cleaned_files:
        print(f"   {cleaned_files} fichier(s) obsolète(s) supprimé(s) de assets/")
    if removed:
        print(f"   {len(removed)} asset(s) retiré(s) du manifest")
    if not changed and not removed:
        print("   aucune modification (manifest déjà à jour)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
