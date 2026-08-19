"""Tests for app/sync.py — reconciliation between Fleasion selection and files.

Covers: analysis, apply (re-copy / clean removal), auto-sync at startup,
unmanaged files, missing sources, restart idempotency.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.backup_manager import BackupManager
from app.file_manager import FileManager
from app.fleasion import FleasionManager
from app.models import KIND_FILE, ConfigItem
from app.scanner import scan_library
from app.sync import SyncEngine, walk_configs


def _fleasion_root(tmp_path: Path, enabled: list[str] | None = None) -> Path:
    """A realistic FleasionNT layout with a known selection."""
    root = tmp_path / "AppData" / "Local" / "FleasionNT"
    root.mkdir(parents=True)
    (root / "configs").mkdir()
    (root / "settings.json").write_text(
        json.dumps({"enabled_configs": enabled or [], "last_config": None}),
        encoding="utf-8",
    )
    return root


def _engine(root: Path, tmp_path: Path) -> SyncEngine:
    backups = tmp_path / "backups"
    bm = BackupManager(backups)
    return SyncEngine(FleasionManager(root / "config", bm), FileManager(bm), bm)


def _read_settings(root: Path) -> dict:
    return json.loads((root / "settings.json").read_text(encoding="utf-8"))


def _charm_item(library: Path) -> ConfigItem:
    node = scan_library(library).node
    charms = next(s for s in node.subdirs if s.name == "Charms")
    return next(c for c in charms.configs if c.name == "nemesis charm")


def test_walk_configs_collects_whole_tree(library: Path) -> None:
    node = scan_library(library).node
    names = {c.name for c in walk_configs(node)}
    assert "nemesis charm" in names      # flat category
    assert "ak-47" in names              # deep skin
    assert "Texture packs" in names      # folder configuration


def test_analyze_reports_missing_files_then_apply_recopies(tmp_path: Path, library: Path) -> None:
    root = _fleasion_root(tmp_path, enabled=["nemesis charm"])
    engine = _engine(root, tmp_path)
    item = _charm_item(library)

    report = engine.analyze([item])
    entry = next(e for e in report.entries if e.name == "nemesis charm")
    assert entry.issue == "missing_files"
    assert entry.state == "active"

    applied = engine.apply(report)
    assert applied.ok
    assert "nemesis charm.json" in applied.copied
    assert (root / "configs" / "nemesis charm.json").exists()
    # Selection was already correct: settings.json untouched.
    assert _read_settings(root)["enabled_configs"] == ["nemesis charm"]

    # Re-analyze: everything is in sync now (restart-safe).
    again = engine.analyze([item])
    assert next(e for e in again.entries if e.name == "nemesis charm").issue == "ok"
    applied2 = engine.apply(again)
    assert applied2.ok
    assert applied2.copied == []


def test_active_config_with_files_is_ok(tmp_path: Path, library: Path) -> None:
    root = _fleasion_root(tmp_path, enabled=["nemesis charm"])
    (root / "configs" / "nemesis charm.json").write_text("{}", encoding="utf-8")
    engine = _engine(root, tmp_path)
    item = _charm_item(library)

    report = engine.analyze([item])
    entry = next(e for e in report.entries if e.name == "nemesis charm")
    assert entry.issue == "ok"
    assert not entry.needs_action

    applied = engine.apply(report)
    assert applied.ok
    assert applied.copied == []
    assert applied.removed == []


def test_stale_copy_reported_but_kept(tmp_path: Path, library: Path) -> None:
    """Files present but not selected are reported and kept by a normal sync."""
    root = _fleasion_root(tmp_path, enabled=[])
    (root / "configs" / "nemesis charm.json").write_text("{}", encoding="utf-8")
    engine = _engine(root, tmp_path)
    item = _charm_item(library)

    report = engine.analyze([item])
    entry = next(e for e in report.entries if e.name == "nemesis charm")
    assert entry.issue == "stale_copy"
    assert entry.state == "copied"

    applied = engine.apply(report)
    assert applied.ok
    assert applied.removed == []
    assert (root / "configs" / "nemesis charm.json").exists()


def test_clean_removes_stale_copy_and_keeps_library(tmp_path: Path, library: Path) -> None:
    root = _fleasion_root(tmp_path, enabled=[])
    (root / "configs" / "nemesis charm.json").write_text("{}", encoding="utf-8")
    engine = _engine(root, tmp_path)
    item = _charm_item(library)

    report = engine.analyze([item], clean=True)
    applied = engine.apply(report)
    assert "nemesis charm.json" in applied.removed
    assert not (root / "configs" / "nemesis charm.json").exists()
    # The library keeps its original: reactivation stays possible.
    assert (library / "Charms" / "nemesis charm.json").exists()
    assert _read_settings(root)["enabled_configs"] == []


def test_clean_removes_only_expected_files(tmp_path: Path, library: Path) -> None:
    """Clean mode removes the item's own files (json + obj) and nothing else."""
    root = _fleasion_root(tmp_path, enabled=[])
    configs = root / "configs"
    (configs / "nemesis charm.json").write_text("{}", encoding="utf-8")
    (configs / "model.obj").write_text("v 0 0 0", encoding="utf-8")
    (configs / "unrelated.json").write_text("{}", encoding="utf-8")

    item = _charm_item(library)
    item.obj = tmp_path / "lib" / "model.obj"
    item.obj_name = "model.obj"

    engine = _engine(root, tmp_path)
    report = engine.analyze([item], clean=True)
    applied = engine.apply(report)
    assert set(applied.removed) == {"nemesis charm.json", "model.obj"}
    assert (configs / "unrelated.json").exists()


def test_clean_refused_without_settings(tmp_path: Path, library: Path) -> None:
    """Without a readable selection, clean removal is refused: safety first."""
    configured = tmp_path / "config"
    configured.mkdir(parents=True)
    (configured / "nemesis charm.json").write_text("{}", encoding="utf-8")
    bm = BackupManager(tmp_path / "backups")
    engine = SyncEngine(FleasionManager(configured, bm), FileManager(bm), bm)

    report = engine.analyze([_charm_item(library)], clean=True)
    applied = engine.apply(report)
    assert applied.removed == []
    assert applied.errors
    assert (configured / "nemesis charm.json").exists()


def test_unmanaged_files_never_touched(tmp_path: Path, library: Path) -> None:
    """Files that belong to no library item are reported but never removed."""
    root = _fleasion_root(tmp_path, enabled=[])
    (root / "configs" / "custom-from-fleasion.json").write_text("{}", encoding="utf-8")
    engine = _engine(root, tmp_path)
    item = _charm_item(library)

    report = engine.analyze([item], clean=True)
    assert any(e.issue == "unmanaged" and e.name == "custom-from-fleasion" for e in report.entries)

    applied = engine.apply(report)
    assert applied.ok
    assert applied.removed == []
    assert (root / "configs" / "custom-from-fleasion.json").exists()


def test_auto_sync_recopies_selected_and_keeps_stale(tmp_path: Path, library: Path) -> None:
    """Startup sync re-copies selected-missing configs and removes nothing."""
    root = _fleasion_root(tmp_path, enabled=["nemesis charm"])
    configs = root / "configs"
    # A stale copy (not selected) that must survive a startup sync.
    (configs / "ak-47.json").write_text("{}", encoding="utf-8")
    engine = _engine(root, tmp_path)

    node = scan_library(library).node
    report = engine.auto_sync(walk_configs(node))
    assert "nemesis charm.json" in report.copied
    assert report.removed == []
    assert report.errors == []
    assert (configs / "nemesis charm.json").exists()
    assert (configs / "ak-47.json").exists()


def test_missing_source_reports_error(tmp_path: Path) -> None:
    """A selected config whose library file disappeared: clean error, no copy."""
    root = _fleasion_root(tmp_path, enabled=["ghost"])
    engine = _engine(root, tmp_path)
    ghost = tmp_path / "lib" / "ghost.json"  # does not exist
    item = ConfigItem(
        name="ghost",
        path=ghost,
        kind=KIND_FILE,
        files=[ghost],
        json_files=[ghost],
    )

    report = engine.analyze([item])
    assert next(e for e in report.entries if e.name == "ghost").issue == "missing_files"

    applied = engine.apply(report)
    assert not applied.ok
    assert any("manquant" in e for e in applied.errors)
    assert not (root / "configs" / "ghost.json").exists()


def test_restore_selection_when_lost(tmp_path: Path, library: Path) -> None:
    """If the selection itself is gone, sync restores files + selection."""
    root = _fleasion_root(tmp_path, enabled=[])  # selection lost
    engine = _engine(root, tmp_path)
    item = _charm_item(library)

    report = engine.analyze([item])
    assert next(e for e in report.entries if e.name == "nemesis charm").issue == "ok"

    # Force the selection to reference the item with missing files, as if
    # settings.json was restored from a backup.
    settings = _read_settings(root)
    settings["enabled_configs"] = ["nemesis charm"]
    (root / "settings.json").write_text(json.dumps(settings), encoding="utf-8")

    report = engine.analyze([item])
    entry = next(e for e in report.entries if e.name == "nemesis charm")
    assert entry.issue == "missing_files"
    applied = engine.apply(report)
    assert applied.ok
    assert (root / "configs" / "nemesis charm.json").exists()
    assert _read_settings(root)["enabled_configs"] == ["nemesis charm"]
