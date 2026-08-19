"""Tests for app/search.py — global search and read-only filters.

Covers: exact/partial/case/whitespace queries, category search (EN/FR
aliases), category + status filters, combinations, canonical result order,
empty results, and the guarantee that nothing is ever modified.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.backup_manager import BackupManager
from app.file_manager import FileManager
from app.fleasion import FleasionManager
from app.scanner import scan_library
from app.search import (
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    STATUS_MISSING,
    STATUS_SYNC,
    SearchState,
    filter_by_category,
    run_search,
)
from app.sync import SyncEngine, walk_configs


def _fleasion_root(tmp_path: Path, enabled: list[str] | None = None) -> Path:
    root = tmp_path / "AppData" / "Local" / "FleasionNT"
    root.mkdir(parents=True)
    (root / "configs").mkdir()
    (root / "settings.json").write_text(
        json.dumps({"enabled_configs": enabled or [], "last_config": None}),
        encoding="utf-8",
    )
    return root


def _engine(root: Path, tmp_path: Path) -> SyncEngine:
    bm = BackupManager(tmp_path / "backups")
    return SyncEngine(FleasionManager(root / "config", bm), FileManager(bm), bm)


def _root(library: Path):
    return scan_library(library).node


def _names(results) -> set[str]:
    return {r.name for r in results}


# ---------------------------------------------------------------------- #
# Query behaviour
# ---------------------------------------------------------------------- #
def test_search_exact(library: Path) -> None:
    results = run_search(_root(library), SearchState("nemesis charm"))
    assert _names(results) == {"nemesis charm"}


def test_search_partial(library: Path) -> None:
    results = run_search(_root(library), SearchState("gun"))
    assert _names(results) == {"Pixelhandgun", "key handgun"}


def test_search_case_insensitive(library: Path) -> None:
    assert _names(run_search(_root(library), SearchState("NEMESIS"))) == {"nemesis charm"}
    assert _names(run_search(_root(library), SearchState("FlossSwap"))) == {"flossswap (1)"}


def test_search_tolerates_extra_spaces(library: Path) -> None:
    assert _names(run_search(_root(library), SearchState("  nemesis   charm  "))) == {
        "nemesis charm"
    }


def test_search_by_category_alias(library: Path) -> None:
    """« primary » and « primaire » both filter the Primary category. The
    category folder itself appears first (exact folder match), then its
    configurations."""
    root = _root(library)
    assert _names(run_search(root, SearchState("primary"))) == {"ak-47", "key up", "Primary"}
    assert _names(run_search(root, SearchState("primaire"))) == {"ak-47", "key up", "Primary"}
    assert _names(run_search(root, SearchState("mêlée"))) == {"NordicAxe", "Melee"}
    assert _names(run_search(root, SearchState("Melee"))) == {"NordicAxe", "Melee"}


def test_search_partial_query_keeps_configs_only(library: Path) -> None:
    """A partial query that matches no folder exactly keeps returning only
    the matching configurations (nothing new, nothing lost)."""
    from app.models import Node

    root = _root(library)
    results = run_search(root, SearchState("gun"))
    assert _names(results) == {"Pixelhandgun", "key handgun"}
    assert not any(isinstance(r, Node) for r in results)


def test_search_exact_folder_prioritized(library: Path, tmp_path: Path) -> None:
    """Searching a weapon name surfaces the folder itself first, before its
    children (Gunblade → Melee/Gunblade, then its skins)."""
    from app.models import Node

    lib = tmp_path / "Skins"
    gun = lib / "Melee" / "Gunblade"
    gun.mkdir(parents=True)
    (gun / "Skin A.json").write_text("{}", encoding="utf-8")
    (gun / "Skin B.json").write_text("{}", encoding="utf-8")

    results = run_search(_root(lib), SearchState("Gunblade"))
    first = results[0]
    assert isinstance(first, Node)
    assert first.name == "Gunblade"
    assert _names(results) == {"Gunblade", "Skin A", "Skin B"}
    assert [r.name for r in results][1:] == ["Skin A", "Skin B"]  # enfants après


def test_search_exact_folder_with_category_filter(library: Path, tmp_path: Path) -> None:
    """The folder result respects the category filter."""
    from app.models import Node

    lib = tmp_path / "Skins"
    (lib / "Melee" / "Gunblade").mkdir(parents=True)
    (lib / "Melee" / "Gunblade" / "A.json").write_text("{}", encoding="utf-8")
    (lib / "Primary" / "Gunblade").mkdir(parents=True)
    (lib / "Primary" / "Gunblade" / "B.json").write_text("{}", encoding="utf-8")

    melee = run_search(_root(lib), SearchState("Gunblade", category="melee"))
    assert any(isinstance(r, Node) and r.name == "Gunblade" for r in melee)
    assert _names(melee) == {"Gunblade", "A"}

    primary = run_search(_root(lib), SearchState("Gunblade", category="primary"))
    assert _names(primary) == {"Gunblade", "B"}


def test_status_filter_drops_folder_results(library: Path, tmp_path: Path) -> None:
    """A status filter only applies to configurations: folder results are
    dropped when one is active (a folder has no activation state)."""
    from app.models import Node

    root = _fleasion_root(tmp_path, enabled=[])
    engine = _engine(root, tmp_path)
    lib = tmp_path / "Skins"
    (lib / "Melee" / "Gunblade").mkdir(parents=True)
    (lib / "Melee" / "Gunblade" / "A.json").write_text("{}", encoding="utf-8")

    results = run_search(_root(lib), SearchState("Gunblade", status=STATUS_INACTIVE), engine)
    assert not any(isinstance(r, Node) for r in results)


def test_search_no_results(library: Path) -> None:
    assert run_search(_root(library), SearchState("zzzzz")) == []


def test_empty_query_returns_everything(library: Path) -> None:
    root = _root(library)
    all_items = walk_configs(root)
    results = run_search(root, SearchState("   "))
    # Every configuration is returned (in canonical order, see the ordering
    # test below), nothing is lost.
    assert _names(results) == _names(all_items)
    assert len(results) == len(all_items)


# ---------------------------------------------------------------------- #
# Filters
# ---------------------------------------------------------------------- #
def test_filter_by_category(library: Path) -> None:
    root = _root(library)
    results = run_search(root, SearchState(""))
    secondary = [r for r in filter_by_category(results, "secondary")]
    assert _names(secondary) == {"Pixelhandgun", "key handgun"}


def test_search_plus_category_filter(library: Path) -> None:
    root = _root(library)
    assert _names(run_search(root, SearchState("key", category="primary"))) == {"key up"}
    assert _names(run_search(root, SearchState("key", category="secondary"))) == {"key handgun"}


def test_status_filter_active_and_inactive(library: Path, tmp_path: Path) -> None:
    root = _fleasion_root(tmp_path, enabled=["ak-47"])
    (root / "configs" / "ak-47.json").write_text("{}", encoding="utf-8")
    engine = _engine(root, tmp_path)
    node = _root(library)

    active = run_search(node, SearchState("", status=STATUS_ACTIVE), engine)
    assert _names(active) == {"ak-47"}

    inactive = run_search(node, SearchState("", status=STATUS_INACTIVE), engine)
    assert "ak-47" not in inactive
    assert "nemesis charm" in _names(inactive)


def test_status_filter_missing_files(library: Path, tmp_path: Path) -> None:
    root = _fleasion_root(tmp_path, enabled=[])
    engine = _engine(root, tmp_path)
    node = _root(library)
    # The source disappears after the scan: the item is still in the tree.
    source = library / "Charms" / "nemesis charm.json"
    source.unlink()

    missing = run_search(node, SearchState("", status=STATUS_MISSING), engine)
    assert _names(missing) == {"nemesis charm"}


def test_status_filter_needs_sync(library: Path, tmp_path: Path) -> None:
    root = _fleasion_root(tmp_path, enabled=["nemesis charm"])
    # nemesis charm: selected but files absent -> missing_files.
    # ak-47: present but not selected -> stale_copy.
    (root / "configs" / "ak-47.json").write_text("{}", encoding="utf-8")
    engine = _engine(root, tmp_path)

    to_sync = run_search(_root(library), SearchState("", status=STATUS_SYNC), engine)
    assert _names(to_sync) == {"nemesis charm", "ak-47"}


def test_category_status_query_combination(library: Path, tmp_path: Path) -> None:
    root = _fleasion_root(tmp_path, enabled=["key handgun"])
    (root / "configs" / "key handgun.json").write_text("{}", encoding="utf-8")
    engine = _engine(root, tmp_path)

    results = run_search(
        _root(library), SearchState("key", category="secondary", status=STATUS_ACTIVE), engine
    )
    assert _names(results) == {"key handgun"}


def test_status_filter_without_engine_returns_nothing(library: Path) -> None:
    """Never guess the activation state without a SyncEngine."""
    results = run_search(_root(library), SearchState("", status=STATUS_ACTIVE), None)
    assert results == []


# ---------------------------------------------------------------------- #
# Ordering + read-only guarantee
# ---------------------------------------------------------------------- #
def test_results_canonical_order(library: Path) -> None:
    results = run_search(_root(library), SearchState(""))
    # Canonical order: primary items first, then secondary, melee, then the
    # rest alphabetically.
    names = [r.name for r in results]
    assert names[0] in ("ak-47", "key up")  # primary
    assert names[1] in ("ak-47", "key up")
    assert names[2] in ("Pixelhandgun", "key handgun")  # secondary
    assert names[3] in ("Pixelhandgun", "key handgun")
    assert names[4] == "NordicAxe"  # melee


def test_search_never_modifies_files(library: Path, tmp_path: Path) -> None:
    def snapshot(root: Path) -> set[tuple[str, int]]:
        return {
            (str(p.relative_to(root)), p.stat().st_size)
            for p in root.rglob("*")
            if p.is_file()
        }

    fleasion = _fleasion_root(tmp_path, enabled=["ak-47"])
    (fleasion / "configs" / "ak-47.json").write_text("{}", encoding="utf-8")
    engine = _engine(fleasion, tmp_path)
    before_lib = snapshot(library)
    before_fleasion = snapshot(fleasion)

    node = _root(library)
    run_search(node, SearchState("key"))
    run_search(node, SearchState("", category="secondary", status=STATUS_ACTIVE), engine)
    run_search(node, SearchState("primaire"))
    run_search(node, SearchState("zzzzz"))

    assert snapshot(library) == before_lib
    assert snapshot(fleasion) == before_fleasion
