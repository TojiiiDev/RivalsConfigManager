"""Batch mod import (v1.3.11) — analyse several sources at once.

The single-item import (``app.mod_import``) treats one ZIP as one mod.
This module adds the batch layer **on top** of it, reusing every existing
mechanism (analysis, safe extraction, detection, staging):

* several files / folders / ZIPs are analysed together;
* a ZIP containing **several independent elements** is split into one
  importable item per element (each top-level mod folder, each loose
  ``.json``/``.obj`` file) — the whole archive is never treated as one
  mod when it actually contains several;
* each element is run through the existing name detection (library
  structure first, known registry, category name) — never a hard-coded
  mod name, never an invented category: when nothing is found the
  destination stays ``None`` and the user picks manually;
* the chosen destinations are resolved by ``app.mod_import.build_plan``
  at install time, so every existing protection (zip-slip, duplicate
  detection, backup before replace, defense-in-depth path checks) is
  unchanged.

Nothing here writes to the library: it only *analyses* and *proposes*.
The final install goes through the unchanged ``install_mod`` pipeline.
"""

from __future__ import annotations

import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import app.mod_import as mod_import
from app.detection import CONFIDENCE_LOW, Detection, detect, suggest_name
from app.i18n import t
from app.mod_import import (
    ModAnalysis,
    ModFile,
    ModImportError,
    _clean_name,
    _is_junk,
    _walk_files,
)

#: Extensions that make a loose top-level file a standalone importable
#: element inside a multi-mod archive (a single mod = one folder, or one
#: such file). Previews/images alone are never an importable element.
_IMPORTABLE_FILE_SUFFIXES = (".json", ".obj", ".mp3")


@dataclass
class BatchItem:
    """One importable element of a batch.

    ``category`` / ``weapon`` start as the automatic detection (when it is
    solid) and stay freely editable per element — changing one element
    never affects the others. ``category`` is ``None`` while the
    destination is unknown: the element is only installed once the user
    chose a real category (never a phantom one).
    """

    source: Path                 # original dropped / selected path
    name: str                    # cleaned mod name (editable before install)
    analysis: ModAnalysis        # its own analysis (with its own staging for zips)
    detected_category: str | None = None
    detected_weapon: str | None = None
    detected_label: str = ""     # human-readable detection summary
    confidence: str = CONFIDENCE_LOW
    origin: str = ""             # display hint for split zip members (« mods.zip > AK47 »)
    category: str | None = None  # chosen category (canonical key or folder name)
    weapon: str | None = None    # chosen weapon (optional)

    @property
    def destination_known(self) -> bool:
        """True once the user chose a real category for this element."""
        return self.category is not None


def analyze_batch(
    paths: list[Path],
    library_root: Path | None = None,
    staging_base: Path | None = None,
) -> tuple[list[BatchItem], list[str]]:
    """Analyse every source of a batch.

    Returns ``(items, errors)``: ``items`` are the importable elements
    (ZIPs with several mods are split); ``errors`` are user-facing
    messages for the sources that could not be analysed (missing file,
    empty archive, bad zip...). A single bad source never blocks the rest
    of the batch.
    """
    items: list[BatchItem] = []
    errors: list[str] = []
    for raw in paths:
        path = Path(raw)
        try:
            if path.is_dir():
                items.extend(_items_from_dir(path))
            elif path.is_file() and path.suffix.lower() == ".zip":
                items.extend(_items_from_zip(path, staging_base))
            elif path.is_file():
                items.append(_item_from_analysis(mod_import.analyze_source(path), path))
            else:
                errors.append(t("mod_import.not_found", path=path))
        except ModImportError as exc:
            errors.append(str(exc))
        except OSError as exc:
            errors.append(str(exc))
    # Détection automatique (structure réelle de la bibliothèque d'abord,
    # registre connu ensuite) — purement indicatif, jamais une catégorie
    # inventée : les destinations inconnues restent à choisir.
    for item in items:
        _apply_detection(item, library_root)
    return items, errors


def cleanup_batch(items: list[BatchItem]) -> None:
    """Remove every staging folder created while analysing the batch
    (no-op for non-zip items; shared staging removed safely)."""
    for item in items:
        mod_import.cleanup_staging(item.analysis)


# ---------------------------------------------------------------------- #
# Per-source analysis
# ---------------------------------------------------------------------- #
def _items_from_dir(folder: Path) -> list[BatchItem]:
    """A dropped folder is one importable element (its name), exactly like
    the single-item import — only ZIPs get the multi-element splitting."""
    return [_item_from_analysis(mod_import.analyze_source(folder), folder)]


def _item_from_analysis(analysis: ModAnalysis, source: Path) -> BatchItem:
    item = BatchItem(
        source=Path(source),
        name=suggest_name(analysis.name),
        analysis=analysis,
        origin="",
    )
    return item


def _items_from_zip(
    zip_path: Path, staging_base: Path | None = None
) -> list[BatchItem]:
    """Analyse a ZIP and split it into one :class:`BatchItem` per
    independent element.

    Rules (generic, never name-based):

    * exactly one top-level folder and no loose files → the whole archive
      is one mod (the common ``Gunblade_Skin/...`` pattern);
    * several top-level folders → one element per folder;
    * loose top-level ``.json`` / ``.obj`` / ``.mp3`` files → one element
      per file (single-file configs); other loose files (previews,
      readme...) are not importable elements;
    * folders + loose importable files → one element per folder and one
      per loose importable file.

    The extraction is the same zip-slip-safe one as the single import
    (``mod_import._safe_extract``); the shared staging folder is recorded
    on every item's analysis so :func:`cleanup_batch` removes it.
    """
    base = staging_base if staging_base is not None else mod_import._staging_base()
    base.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix="batch_import_", dir=str(base)))
    try:
        mod_import._safe_extract(zip_path, staging)
        entries = sorted(staging.iterdir())
        dirs = [e for e in entries if e.is_dir()]
        files = [e for e in entries if e.is_file() and not _is_junk(e.name)]

        roots: list[tuple[Path, str]] = []  # (root, display name)
        if len(dirs) == 1 and not files:
            roots.append((dirs[0], dirs[0].name))
        else:
            for folder in dirs:
                roots.append((folder, folder.name))
            for file in files:
                if file.suffix.lower() in _IMPORTABLE_FILE_SUFFIXES:
                    roots.append((file, file.stem))

        items: list[BatchItem] = []
        for root, display in roots:
            if root.is_dir():
                files_list = _walk_files(root)
                name = _clean_name(root.name)
                analysis = ModAnalysis(
                    name=name, root=root, files=files_list, kind="zip", staging=staging
                )
            else:
                files_list = [ModFile(root.name, root.stat().st_size)]
                analysis = ModAnalysis(
                    name=_clean_name(root.stem),
                    root=staging,
                    files=files_list,
                    kind="zip",
                    staging=staging,
                )
            if not analysis.files:
                continue  # dossier vide dans l'archive : rien d'importable
            item = BatchItem(
                source=Path(zip_path),
                name=suggest_name(analysis.name),
                analysis=analysis,
                origin=display,
            )
            items.append(item)
        if not items:
            raise ModImportError(
                t("mod_import.empty_archive", name=zip_path.name)
            )
        return items
    except ModImportError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    except (zipfile.BadZipFile, OSError) as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise ModImportError(
            t(
                "mod_import.bad_archive",
                name=zip_path.name,
                detail=getattr(exc, "strerror", None) or exc,
            )
        ) from exc


# ---------------------------------------------------------------------- #
# Detection
# ---------------------------------------------------------------------- #
def _apply_detection(item: BatchItem, library_root: Path | None) -> None:
    """Pre-fill the destination from the existing detection rules when the
    evidence is solid; otherwise leave the destination to the user.

    The category is only ever a real library folder or a canonical weapon
    category (created by the installer) — never invented from the name.
    """
    det: Detection = detect(item.name, library_root)
    item.confidence = det.confidence
    item.detected_category = det.category
    item.detected_weapon = det.weapon
    item.detected_label = det.label
    if det.category is not None and det.confidence != CONFIDENCE_LOW:
        item.category = det.category
        item.weapon = det.weapon
