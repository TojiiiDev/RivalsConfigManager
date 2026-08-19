"""Mod import — analyse a source, detect duplicates, install safely.

Accepts three kinds of sources:

* a **ZIP** archive (extracted into a staging folder, never directly);
* a **folder**;
* a single **file** (``.obj``, ``.json``, ...).

The pipeline is:

1. :func:`analyze_source` — inspect the source, extract archives with a
   **zip-slip guard** (``../``, absolute paths and drive letters are
   refused), compute the mod name and the list of files;
2. :func:`build_plan` — resolve the destination inside the library
   (``<library>/<Catégorie>/[<arme>/]<mod>/``), detect duplicates (same
   name, same file, same content hash);
3. :func:`install_mod` — copy the files into the library, backing up any
   replaced mod first. Every path is validated again at install time
   (defense in depth): a mod-provided path can never escape the
   destination.

Everything a mod provides (paths inside archives, relative names) is
treated as untrusted input.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from .categories import folder_name_for
from .config import data_dir
from .i18n import t

#: Junk entries always ignored when analysing a source.
_JUNK_NAMES = {".ds_store", "thumbs.db"}

#: Default duplicate mode when the user does not choose.
MODE_KEEP_BOTH = "keep_both"
MODE_REPLACE = "replace"
MODE_CANCEL = "cancel"


class ModImportError(Exception):
    """User-facing error with a clear message."""


@dataclass
class ModFile:
    """One file of a mod, by normalized relative path."""

    rel: str          # posix relative path, never ``..``, never absolute
    size: int


@dataclass
class ModAnalysis:
    """What a source contains, before any installation."""

    name: str
    root: Path         # staging subfolder (zip) or the source itself
    files: list[ModFile]
    kind: str          # "zip" | "dir" | "file"
    staging: Path | None = None   # the mkdtemp dir to clean up (zips only)

    @property
    def obj_count(self) -> int:
        return sum(1 for f in self.files if f.rel.lower().endswith(".obj"))

    @property
    def json_count(self) -> int:
        return sum(1 for f in self.files if f.rel.lower().endswith(".json"))

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)


@dataclass
class Duplicate:
    """A possible collision between the mod being imported and the library."""

    kind: str          # "name" | "hash" | "file"
    existing: Path
    details: str


@dataclass
class InstallPlan:
    """What :func:`install_mod` will do — shown to the user first."""

    name: str
    category: str      # canonical category key
    weapon: str | None
    destination: Path
    root: Path
    files: list[ModFile]
    duplicates: list[Duplicate]
    mode: str = MODE_KEEP_BOTH


# ---------------------------------------------------------------------- #
# Source analysis
# ---------------------------------------------------------------------- #
def analyze_source(path: Path, staging_base: Path | None = None) -> ModAnalysis:
    """Inspect a ZIP / folder / file and return its analysis.

    Raises :class:`ModImportError` for dangerous or unreadable sources.
    ZIPs are extracted into a staging folder (cleaned by the caller with
    :func:`cleanup_staging`). ``staging_base`` is injectable for tests.
    """
    path = Path(path)
    if path.is_dir():
        return _analyze_dir(path)
    if not path.is_file():
        raise ModImportError(t("mod_import.not_found", path=path))
    if path.suffix.lower() == ".zip":
        return _analyze_zip(path, staging_base)
    # A single file (obj / json / image ...): the mod is that file. Its
    # own name is already a safe relative path (no separators).
    return ModAnalysis(
        name=_clean_name(path.stem),
        root=path.parent,
        files=[ModFile(path.name, path.stat().st_size)],
        kind="file",
    )


def cleanup_staging(analysis: ModAnalysis) -> None:
    """Remove the staging folder created for a ZIP (no-op otherwise)."""
    if analysis.staging is not None:
        shutil.rmtree(analysis.staging, ignore_errors=True)


def _analyze_dir(folder: Path) -> ModAnalysis:
    try:
        files = _walk_files(folder)
    except OSError as exc:
        raise ModImportError(
            t("mod_import.read_failed", folder=folder, detail=exc.strerror or exc)
        ) from exc
    if not files:
        raise ModImportError(t("mod_import.empty_folder", folder=folder))
    return ModAnalysis(
        name=_clean_name(folder.name),
        root=folder,
        files=files,
        kind="dir",
    )


def _analyze_zip(zip_path: Path, staging_base: Path | None = None) -> ModAnalysis:
    base = staging_base if staging_base is not None else _staging_base()
    base.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="mod_import_", dir=str(base)))
    try:
        _safe_extract(zip_path, staging)
        root = _unwrap_single_folder(staging)
        name = _clean_name(root.name) if root != staging else _clean_name(zip_path.stem)
        files = _walk_files(root)
    except ModImportError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if not files:
        shutil.rmtree(staging, ignore_errors=True)
        raise ModImportError(t("mod_import.empty_archive", name=zip_path.name))
    return ModAnalysis(name=name, root=root, files=files, kind="zip", staging=staging)


def _staging_base() -> Path:
    base = data_dir() / "import_staging"
    base.mkdir(parents=True, exist_ok=True)
    return base


# ---------------------------------------------------------------------- #
# Zip-slip-safe extraction
# ---------------------------------------------------------------------- #
def _safe_extract(zip_path: Path, dest_dir: Path) -> None:
    """Extract an archive, refusing every entry that could escape
    ``dest_dir`` (``../``, absolute paths, drive letters, backslashes)."""
    dest_resolved = dest_dir.resolve()
    try:
        with zipfile.ZipFile(zip_path) as zf:
            for info in zf.infolist():
                rel = _safe_normalize(info.filename)
                if rel is None:
                    raise ModImportError(
                        t(
                            "mod_import.dangerous_entry",
                            name=zip_path.name,
                            entry=info.filename,
                        )
                    )
                target = (dest_dir / rel).resolve()
                if not _is_within(target, dest_resolved):
                    raise ModImportError(
                        t(
                            "mod_import.escapes",
                            name=zip_path.name,
                            entry=info.filename,
                        )
                    )
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
    except (zipfile.BadZipFile, OSError) as exc:
        raise ModImportError(
            t(
                "mod_import.bad_archive",
                name=zip_path.name,
                detail=getattr(exc, "strerror", None) or exc,
            )
        ) from exc


# ---------------------------------------------------------------------- #
# Planning + duplicates
# ---------------------------------------------------------------------- #
def build_plan(
    name: str,
    category: str,
    weapon: str | None,
    analysis: ModAnalysis,
    library_root: Path,
    mode: str = MODE_KEEP_BOTH,
) -> InstallPlan:
    """Resolve the destination and detect duplicates for the given choices."""
    safe_name = _sanitize_component(name) or "mod"
    destination = _destination(library_root, category, weapon, safe_name)
    # Defense in depth: the destination must always stay inside the
    # library root — never under ``../``, a drive letter or an absolute
    # path, whatever the category/weapon/name supplied.
    library_resolved = Path(library_root).resolve()
    if not _is_within(destination.resolve(), library_resolved):
        raise ModImportError(
            t("mod_import.destination_refused", dest=destination)
        )
    duplicates = find_duplicates(analysis.root, destination, analysis.files)
    return InstallPlan(
        name=safe_name,
        category=category,
        weapon=_sanitize_component(weapon) if weapon else None,
        destination=destination,
        root=analysis.root,
        files=list(analysis.files),
        duplicates=duplicates,
        mode=mode,
    )


def find_duplicates(
    root: Path, destination: Path, files: list[ModFile]
) -> list[Duplicate]:
    """Collisions between the mod and the destination (name, file, hash)."""
    duplicates: list[Duplicate] = []
    if destination.exists():
        duplicates.append(
            Duplicate(
                "name",
                destination,
                t("mod_import.dup_same_name"),
            )
        )
    seen: set[str] = set()
    for f in files:
        existing = destination / f.rel
        if not existing.is_file() or f.rel.lower() in seen:
            continue
        seen.add(f.rel.lower())
        same = _same_content(root / f.rel, existing)
        detail = t("mod_import.dup_exists", rel=f.rel)
        if same:
            detail += t("mod_import.dup_identical")
            duplicates.append(Duplicate("hash", existing, detail))
        else:
            detail += t("mod_import.dup_different")
            duplicates.append(Duplicate("file", existing, detail))
    return duplicates


# ---------------------------------------------------------------------- #
# Installation
# ---------------------------------------------------------------------- #
def install_mod(plan: InstallPlan, backup_manager=None) -> Path:
    """Copy the mod into the library. Returns the destination folder.

    ``replace`` backs up the existing mod (with ``backup_manager``) before
    removing it; ``keep_both`` installs under ``nom (2)`` when needed.
    Every relative path is re-validated before being copied.
    """
    destination = plan.destination

    if plan.mode == MODE_REPLACE and destination.exists():
        _backup_destination(destination, backup_manager)
        shutil.rmtree(destination, ignore_errors=True)
    elif plan.mode == MODE_KEEP_BOTH and destination.exists():
        destination = _next_free_name(destination)

    root_resolved = plan.root.resolve()
    destination.mkdir(parents=True, exist_ok=True)

    for f in plan.files:
        rel = _safe_normalize(f.rel)
        if rel is None:
            raise ModImportError(t("mod_import.invalid_path", rel=f.rel))
        src = (plan.root / rel).resolve()
        if not _is_within(src, root_resolved):
            raise ModImportError(t("mod_import.escapes_path", rel=f.rel))
        if not src.is_file():
            raise ModImportError(t("mod_import.missing_in_mod", rel=f.rel))
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy2(src, target)
        except OSError as exc:
            raise ModImportError(
                t("mod_import.copy_failed", rel=f.rel, detail=exc.strerror or exc)
            ) from exc
    return destination


def _backup_destination(destination: Path, backup_manager) -> None:
    files = [p for p in destination.rglob("*") if p.is_file()]
    if not files:
        return
    if backup_manager is None:
        raise ModImportError(t("mod_import.no_backup_replace"))
    try:
        backup_manager.create_backup(files)
    except (OSError, ValueError) as exc:
        raise ModImportError(t("mod_import.backup_failed")) from exc


# ---------------------------------------------------------------------- #
# Helpers
# ---------------------------------------------------------------------- #
def _walk_files(root: Path) -> list[ModFile]:
    files: list[ModFile] = []
    for p in sorted(root.rglob("*")):
        if not p.is_file() or _is_junk(p.relative_to(root).as_posix()):
            continue
        rel = _safe_normalize(p.relative_to(root).as_posix())
        if rel is None:
            continue
        files.append(ModFile(rel, p.stat().st_size))
    return files


def _unwrap_single_folder(staging: Path) -> Path:
    """If the archive has exactly one top-level folder, use it as the mod
    root (common pattern: ``Gunblade_Skin/...`` inside the zip)."""
    entries = [p for p in staging.iterdir()]
    dirs = [p for p in entries if p.is_dir()]
    files = [p for p in entries if p.is_file() and not _is_junk(p.name)]
    if len(dirs) == 1 and not files:
        return dirs[0]
    return staging


def _is_junk(rel: str) -> bool:
    parts = Path(rel).parts
    if "__MACOSX" in parts:
        return True
    return any(part.lower() in _JUNK_NAMES for part in parts)


def _safe_normalize(rel: str) -> str | None:
    """Normalize a relative path; ``None`` when it is unsafe (absolute,
    drive letter, ``..``, empty)."""
    if not rel:
        return None
    posix = rel.replace("\\", "/")
    while posix.startswith("./"):
        posix = posix[2:]
    if posix.startswith("/"):
        return None
    if len(posix) >= 2 and posix[1] == ":":
        return None
    parts = posix.split("/")
    if any(part in ("", "..") for part in parts):
        return None
    return "/".join(parts)


def _clean_name(stem: str) -> str:
    name = " ".join(stem.replace("_", " ").replace("-", " ").split())
    return name or stem


def _sanitize_component(text: str) -> str:
    """A safe single folder-name component (no separators, no dots-only)."""
    cleaned = "".join(
        c for c in text.strip() if c not in '/\\:*?"<>|'
    ).strip(" .")
    return cleaned


def _destination(
    library_root: Path, category: str, weapon: str | None, name: str
) -> Path:
    # A canonical category (Primary / Secondary / Melee / Utility) may live
    # anywhere in the library (the real library organises them under
    # ``rivals skins/``). Resolve the EXISTING folder first — a weapon is
    # never dropped into a brand-new root-level ``Primary`` while the real
    # one exists elsewhere. Falls back to ``<library>/<Primary>`` (the
    # canonical layout the installer creates) only when no folder exists.
    from .categories import resolve_category_folder

    folder = resolve_category_folder(library_root, category)
    if folder is None:
        folder = Path(library_root) / folder_name_for(category)
    dest = folder
    if weapon:
        dest = dest / _sanitize_component(weapon)
    return dest / name


def _next_free_name(destination: Path) -> Path:
    suffix = 2
    candidate = destination.parent / f"{destination.name} ({suffix})"
    while candidate.exists():
        suffix += 1
        candidate = destination.parent / f"{destination.name} ({suffix})"
    return candidate


def _same_content(a: Path, b: Path) -> bool:
    try:
        if a.stat().st_size != b.stat().st_size:
            return False
    except OSError:
        return False
    return _sha1(a) == _sha1(b)


def _sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_within(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False
