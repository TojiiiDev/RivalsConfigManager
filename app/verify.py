"""Configuration verification — is a configuration actually usable?

The « Vérifier » button (v1.3.0) runs a real check instead of the old
« Synchroniser » label. :func:`verify_item` analyses one configuration and
reports, section by section:

* **JSON** — every JSON file exists, is parseable and structurally usable
  (reuses :mod:`app.json_validator` for the detailed errors);
* **Dépendances** — the OBJ / MP3 analysis from
  :mod:`app.config_analysis` (present vs. missing, per file) — never a
  second dependency scanner;
* **Fichiers** — every file of the item actually exists on disk;
* **Catégorie** — the configuration sits in a real folder inside the
  library (canonical category or a user folder).

The result is a structured :class:`ConfigVerification` with a clear
``valid`` flag (« Configuration valide » / « Configuration incomplète »)
and a precise list of problems — the UI never claims a configuration is
usable while a required dependency is missing.

Nothing in this module writes, moves or deletes any file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .categories import category_of_path
from .config_analysis import ConfigDependencies, analyze_item
from .i18n import t
from .json_validator import validate_files
from .models import ConfigItem


@dataclass
class ConfigVerification:
    """Result of :func:`verify_item` — section by section, never guessed."""

    valid: bool = False
    # -- JSON ------------------------------------------------------------ #
    json_ok: bool = False
    json_errors: list[str] = field(default_factory=list)
    # -- Dependencies (reused from config_analysis) ---------------------- #
    deps: ConfigDependencies = field(default_factory=ConfigDependencies)
    # -- Files ----------------------------------------------------------- #
    files_ok: bool = True
    files_missing: list[str] = field(default_factory=list)
    # -- Category -------------------------------------------------------- #
    category_ok: bool = True
    category: str | None = None

    # ------------------------------------------------------------------ #
    @property
    def incomplete(self) -> bool:
        """True when at least one problem blocks a clean activation."""
        return not self.valid

    @property
    def problems(self) -> list[str]:
        """Human-readable list of every problem found (translated)."""
        problems: list[str] = []
        if not self.json_ok:
            problems.extend(self.json_errors)
        if self.deps.obj_required and self.deps.missing_obj_files:
            for name in self.deps.missing_obj_files:
                problems.append(t("verify.missing_dependency", kind="OBJ", name=name))
        if self.deps.mp3_required and self.deps.missing_mp3_files:
            for name in self.deps.missing_mp3_files:
                problems.append(t("verify.missing_dependency", kind="MP3", name=name))
        for name in self.files_missing:
            problems.append(t("verify.missing_file", name=name))
        if not self.category_ok:
            problems.append(t("verify.invalid_category"))
        return problems


def verify_item(item: ConfigItem) -> ConfigVerification:
    """Verify a library :class:`ConfigItem` in full.

    Read-only. Reuses the existing JSON validator and the existing OBJ/MP3
    dependency analysis — no second scanner is ever built.
    """
    if item is None:
        return ConfigVerification(valid=False)

    # -- JSON ------------------------------------------------------------ #
    json_paths = [p for p in item.json_files if p.suffix.lower() == ".json"]
    if json_paths:
        json_ok, json_errors = validate_files(json_paths)
    else:
        json_ok, json_errors = False, [t("verify.no_json")]
    if not json_ok:
        # An invalid JSON makes the dependencies unknown: no claim at all.
        return ConfigVerification(
            valid=False,
            json_ok=False,
            json_errors=json_errors,
            deps=ConfigDependencies(valid=False),
            files_ok=all(p.exists() for p in item.files),
            files_missing=[p.name for p in item.files if not p.exists()],
            category_ok=_category_ok(item),
            category=category_of_path(item.path) or item.path.parent.name,
        )

    # -- Dependencies (reuse config_analysis, cached parses) ------------- #
    deps = analyze_item(item)

    # -- Files ----------------------------------------------------------- #
    files_missing = [p.name for p in item.files if not p.exists()]
    for o in item.objs:
        if not o.exists():
            files_missing.append(o.name)
    files_ok = not files_missing

    # -- Category -------------------------------------------------------- #
    category_ok = _category_ok(item)
    category = category_of_path(item.path) or item.path.parent.name

    valid = (
        json_ok
        and files_ok
        and category_ok
        and not deps.incomplete
    )
    return ConfigVerification(
        valid=valid,
        json_ok=True,
        json_errors=[],
        deps=deps,
        files_ok=files_ok,
        files_missing=files_missing,
        category_ok=category_ok,
        category=category,
    )


def _category_ok(item: ConfigItem) -> bool:
    """A configuration sits in a valid category when its parent folder is a
    real directory inside the library (canonical category or user folder).
    A stale item whose folder disappeared is flagged."""
    parent = item.path.parent
    return parent.is_dir()
