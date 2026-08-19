"""Synchronisation engine: declared activation state <-> real files.

Reconciles the four sources involved in activation:

* the library (source of truth — the original files),
* Fleasion's selection (``settings.json`` / ``enabled_configs``),
* the files actually present in Fleasion's config folder,
* the application cache (never touched by the engine).

A **normal** sync is conservative: it only *adds* what is missing (a
selected configuration whose files disappeared from the active folder is
re-copied from the library). It never removes anything.

**Clean** mode additionally removes the copies of library items that are
*not* selected (they stay available in the library, so activation is always
possible again). Clean mode requires the Fleasion selection to be readable
— without it, removal is refused — and it is meant to run behind an
explicit user confirmation.

Files in the active folder that belong to no library item (e.g. created
inside Fleasion itself) are reported but **never** touched, in either mode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .backup_manager import BackupManager
from .file_manager import FileManager
from .fleasion import FleasionManager, config_name
from .i18n import t
from .models import ConfigItem, Node

#: Issue labels produced by :meth:`SyncEngine.analyze`.
ISSUE_OK = "ok"
ISSUE_MISSING_FILES = "missing_files"
ISSUE_STALE_COPY = "stale_copy"
ISSUE_UNMANAGED = "unmanaged"


def walk_configs(node: Node) -> list[ConfigItem]:
    """Every configuration in the tree (direct configs + all sub-folders)."""
    items = list(node.configs)
    for sub in node.subdirs:
        items.extend(walk_configs(sub))
    return items


@dataclass
class SyncEntry:
    """One configuration's state compared with the real files."""

    name: str
    state: str                       # active / copied / inactive / unknown
    issue: str                       # ISSUE_*
    item: ConfigItem | None = None
    files: list[str] = field(default_factory=list)

    @property
    def needs_action(self) -> bool:
        return self.issue in (ISSUE_MISSING_FILES, ISSUE_STALE_COPY)


@dataclass
class SyncReport:
    """Outcome of an analysis and of an (optional) application pass."""

    entries: list[SyncEntry] = field(default_factory=list)
    copied: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    clean: bool = False

    def summary(self) -> str:
        parts = []
        if self.copied:
            n = len(self.copied)
            suffix = "s" if n > 1 else ""
            parts.append(t("outcome.recopied_files", count=n, s=suffix))
        if self.removed:
            n = len(self.removed)
            suffix = "s" if n > 1 else ""
            parts.append(t("outcome.removed_files", count=n, s=suffix))
        if not parts:
            parts.append(t("outcome.all_synced"))
        return ", ".join(parts)

    @property
    def ok(self) -> bool:
        return not self.errors


class SyncEngine:
    """Compare and fix the activation state against the real files."""

    def __init__(
        self,
        fleasion: FleasionManager,
        file_manager: FileManager,
        backup_manager: BackupManager,
    ) -> None:
        self.fleasion = fleasion
        self.file_manager = file_manager
        self.backup_manager = backup_manager

    # ------------------------------------------------------------------ #
    def analyze(self, items: list[ConfigItem], clean: bool = False) -> SyncReport:
        """Compare every item with the real files. Never writes to disk."""
        report = SyncReport(clean=clean)
        info = self.fleasion.detect()
        config_dir = info.config_dir
        if config_dir is None:
            report.errors.append(t("toast.fleasion_not_configured_short"))
            return report

        enabled = set(info.enabled_configs)
        known: set[str] = set()

        for item in items:
            name = config_name(item)
            known.add(name)
            expected = self._expected_names(item)
            key = config_dir / f"{name}.json"
            selected = name in enabled
            present = key.is_file()

            if selected and not present:
                issue = ISSUE_MISSING_FILES
            elif present and not selected:
                issue = ISSUE_STALE_COPY
            else:
                issue = ISSUE_OK
            entry = SyncEntry(
                name=name,
                state="active" if selected else ("copied" if present else "inactive"),
                issue=issue,
                item=item,
                files=expected,
            )
            report.entries.append(entry)

        # Files present in the active folder but belonging to no library
        # item: reported, never touched.
        try:
            active = sorted(
                (p for p in config_dir.iterdir() if p.suffix.lower() == ".json"),
                key=lambda p: p.name.lower(),
            )
        except OSError:
            active = []
        for p in active:
            if p.stem not in known:
                report.entries.append(
                    SyncEntry(name=p.stem, state="unknown", issue=ISSUE_UNMANAGED, files=[p.name])
                )
        return report

    # ------------------------------------------------------------------ #
    def apply(self, report: SyncReport, backup_before_overwrite: bool = True) -> SyncReport:
        """Execute the planned fixes (mutates and returns ``report``)."""
        info = self.fleasion.detect()
        config_dir = info.config_dir
        if config_dir is None:
            report.errors.append(t("toast.fleasion_not_configured_short"))
            return report
        enabled = set(info.enabled_configs)

        for entry in report.entries:
            if entry.issue == ISSUE_MISSING_FILES and entry.item is not None:
                self._restore(entry, config_dir, enabled, report, backup_before_overwrite)
            elif entry.issue == ISSUE_STALE_COPY and report.clean:
                if not info.found:
                    report.errors.append(t("sync.selection_unreadable", name=entry.name))
                    continue
                if entry.item is None:
                    continue
                result = self.file_manager.remove_copies(
                    entry.item, config_dir, backup_before_overwrite
                )
                report.removed.extend(result.removed)
                report.errors.extend(result.errors)
        return report

    # ------------------------------------------------------------------ #
    def sync_item(self, item: ConfigItem, backup_before_overwrite: bool = True) -> SyncReport:
        """Analyze one item and fix it (used by the « Synchroniser » button)."""
        report = self.analyze([item])
        self.apply(report, backup_before_overwrite)
        return report

    # ------------------------------------------------------------------ #
    def auto_sync(self, items: list[ConfigItem]) -> SyncReport:
        """Startup reconciliation: re-copy selected configs whose files
        disappeared from the active folder. Never removes anything."""
        report = self.analyze(items, clean=False)
        report.entries = [e for e in report.entries if e.issue == ISSUE_MISSING_FILES]
        self.apply(report)
        return report

    # ------------------------------------------------------------------ #
    def _restore(
        self,
        entry: SyncEntry,
        config_dir: Path,
        enabled: set[str],
        report: SyncReport,
        backup_before_overwrite: bool,
    ) -> None:
        """Re-copy a selected configuration whose files are missing."""
        item = entry.item
        assert item is not None
        if entry.name in enabled:
            # Selection is already correct: only the files are missing.
            copy = self.file_manager.activate(item, config_dir, backup_before_overwrite)
            report.copied.extend(copy.copied)
            if not copy.ok:
                report.errors.extend(copy.errors)
        else:
            # Selection itself was lost: restore files and selection.
            outcome = self.fleasion.activate(item, self.file_manager, backup_before_overwrite)
            report.copied.extend(outcome.copied)
            if not outcome.ok:
                report.errors.extend(outcome.errors)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _expected_names(item: ConfigItem) -> list[str]:
        """The file names this item places in the active folder."""
        names = [p.name for p in item.files]
        if item.obj is not None and item.obj_name and item.obj_name not in names:
            names.append(item.obj_name)
        return names
