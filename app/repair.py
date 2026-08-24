"""Repair plans — fix a configuration's missing dependencies, conservatively.

When a configuration is incomplete (« Vérifier » found missing OBJ/MP3
files), :func:`build_repair_plan` looks for each missing file in **known,
safe locations** and, when found, proposes copying it next to the JSON:

* the configuration's **associated model** (the app's obj cache): when the
  item has an associated ``.obj`` (stored in the cache) whose destination
  name matches the missing reference, the cached file is copied next to
  the JSON — the canonical « dependency detected but file moved » case;
* **the library itself**: a same-named file (case-insensitive) living in
  another folder of the library is a strong signal the file was simply
  moved — a copy is proposed.

Rules (hard):

* repair only ever **copies** — never moves, never deletes, never
  overwrites an existing file (a target that already exists is skipped);
* the destination is always the JSON's own folder (``folder / basename``)
  — ``../``, absolute paths and drive letters are structurally impossible;
* if a missing file has no candidate, the plan says so explicitly
  (« Impossible de réparer automatiquement ») with the file listed;
* the plan must be **confirmed by the user** before anything is copied;
* after applying, the caller must **re-verify** with
  :func:`app.verify.verify_item` — « Réparé » is only ever shown when the
  re-verification really confirms the configuration is complete.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .config import obj_cache_dir
from .i18n import t
from .models import ConfigItem
from .verify import ConfigVerification


@dataclass
class RepairAction:
    """One concrete copy to perform (always a copy, never a move)."""

    source: Path
    target: Path

    @property
    def description(self) -> str:
        return t("repair.action_copy", name=self.target.name)


@dataclass
class RepairPlan:
    """What can (and cannot) be repaired for one configuration."""

    possible: bool = False
    actions: list[RepairAction] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)   # unrecoverable files

    @property
    def explanation(self) -> str:
        """Human-readable summary of the plan (translated)."""
        if self.possible:
            n = len(self.actions)
            return t("repair.possible", count=n, s="" if n == 1 else "s")
        if self.missing:
            return t(
                "repair.impossible",
                files="\n".join(f"• {name}" for name in self.missing),
            )
        return t("repair.nothing")


def build_repair_plan(
    item: ConfigItem,
    verification: ConfigVerification,
    library_root: Path | None = None,
    obj_cache: Path | None = None,
) -> RepairPlan:
    """Find safe copy sources for every missing dependency.

    Never raises. ``library_root`` (the user's library folder) enables the
    « file moved elsewhere in the library » search; ``obj_cache`` defaults
    to the application's obj cache directory.
    """
    plan = RepairPlan()
    if verification is None or verification.deps is None:
        return plan

    deps = verification.deps
    missing_names = list(deps.missing_obj_files) + list(deps.missing_mp3_files)
    if not missing_names:
        plan.possible = True  # nothing missing: nothing to repair
        return plan

    folder = item.path.parent if not item.is_folder else item.path
    cache = Path(obj_cache) if obj_cache is not None else obj_cache_dir()

    for name in missing_names:
        # 1. The item's own associated model (app obj cache).
        source = _candidate_from_associated(item, name, cache)
        # 2. The library: a same-named file elsewhere (moved file).
        if source is None and library_root is not None:
            source = _candidate_in_library(Path(library_root), name, folder)
        if source is None:
            plan.missing.append(name)
            continue
        target = folder / name
        if target.exists():
            # Never overwrite: the file is actually there now.
            continue
        plan.actions.append(RepairAction(source=source, target=target))

    plan.possible = bool(plan.actions) and not plan.missing
    return plan


def apply_repair(plan: RepairPlan, backup_manager=None) -> list[str]:
    """Execute the plan (copies only). Returns a list of errors (empty = ok).

    Each copy is validated again at apply time: the source must exist and
    the target must not exist (never overwrite). Backs up nothing — the
    target does not exist by construction.
    """
    errors: list[str] = []
    for action in plan.actions:
        if not action.source.is_file():
            errors.append(t("repair.source_missing", name=action.source.name))
            continue
        if action.target.exists():
            continue  # already there — nothing to do
        try:
            action.target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(action.source, action.target)
        except OSError as exc:
            errors.append(
                t(
                    "repair.copy_failed",
                    name=action.target.name,
                    detail=exc.strerror or exc,
                )
            )
    return errors


# ---------------------------------------------------------------------- #
# Candidates
# ---------------------------------------------------------------------- #
def _candidate_from_associated(
    item: ConfigItem, name: str, cache: Path
) -> Path | None:
    """The cached model when its destination name matches the reference."""
    for obj_path, obj_name in zip(item.objs, item.obj_names):
        if not obj_path.is_file():
            continue
        dest_name = obj_name or obj_path.name
        if dest_name.casefold() == name.casefold():
            return obj_path
    # The cache stores the model under the stable id — check the raw name.
    cached = cache / name
    return cached if cached.is_file() else None


def _candidate_in_library(
    library_root: Path, name: str, current_folder: Path
) -> Path | None:
    """A same-named file elsewhere in the library (bounded walk)."""
    wanted = name.casefold()
    try:
        entries = sorted(library_root.rglob("*"), key=lambda p: str(p).casefold())
    except OSError:
        return None
    for path in entries:
        if not path.is_file():
            continue
        if path.name.casefold() != wanted:
            continue
        # Never propose copying a file from the configuration's own folder
        # (it would be the very file we claim is missing — a false lead).
        try:
            path.relative_to(current_folder)
            continue
        except ValueError:
            pass
        return path
    return None
