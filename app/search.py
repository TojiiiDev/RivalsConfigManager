"""Global search and result filters — read-only.

A :class:`SearchState` describes the whole search context (query, category
filter, status filter) so it can be stored in the navigation history and
restored by back/forward.

The category filter uses :func:`app.categories.category_of_path`; the
status filter reuses the :class:`app.sync.SyncEngine` analysis instead of
reimplementing activation logic. Nothing in this module moves, deletes or
modifies any file.
"""

from __future__ import annotations

from dataclasses import dataclass

from .categories import category_name_matches_exact, category_of_path, category_rank
from .fleasion import config_name
from .models import ConfigItem, Node
from .scanner import search_library
from .sync import SyncEngine, SyncEntry, walk_configs

#: Status filter keys (None = no filter).
STATUS_ALL = "all"
STATUS_ACTIVE = "active"
STATUS_INACTIVE = "inactive"
STATUS_MISSING = "missing"
STATUS_SYNC = "sync"

#: Favorites filter keys (1.3.0) — ``None`` = no filter.
FAVORITES_ALL = "all"
FAVORITES_ONLY = "fav"
FAVORITES_EXCLUDED = "nofav"


def _favorites_value(value: str | None) -> str | None:
    """Normalize a favorites filter (unknown -> None)."""
    if value in (FAVORITES_ONLY, FAVORITES_EXCLUDED):
        return value
    return None


@dataclass
class SearchState:
    """A search context: query + optional category, status and favorites
    filters."""

    query: str
    category: str | None = None   # canonical category key (primary, ...)
    status: str | None = None     # STATUS_* key
    favorites: str | None = None  # FAVORITES_* key (None = all)


def run_search(
    root_node: Node,
    state: SearchState,
    sync_engine: SyncEngine | None = None,
    favorite_keys: set[str] | None = None,
) -> list:
    """Apply the query, category, status and favorites filters, then sort
    the results.

    Hierarchical results: when a **folder** matches the query exactly, the
    folder itself is returned as a result, **before** its children (e.g.
    searching « Gunblade » shows ``Melee/Gunblade`` first, then the skins
    it contains). Partial queries keep returning only the matching
    configurations. The results are sorted in canonical order (Primaire →
    Secondaire → Mêlée → Utilitaire, then alphabetical). Read-only.

    A status filter requires a :class:`SyncEngine` (its analysis is reused);
    without one, no result is guessed — an empty list is returned. When a
    status filter is active, folder results are dropped (a folder has no
    activation state).
    """
    if root_node is None:
        return []

    query = " ".join(state.query.split())
    if query:
        results = search_library(root_node, query)
        folders = _exact_folder_matches(root_node, query)
    else:
        results = walk_configs(root_node)
        folders = []

    results = filter_by_category(results, state.category)
    if state.category:
        folders = [f for f in folders if category_of_path(f.path) == state.category]

    if state.status and state.status != STATUS_ALL:
        if sync_engine is None:
            return []
        index = build_state_index(results, sync_engine)
        results = filter_by_status(results, state.status, index)
        folders = []  # un dossier n'a pas d'état d'activation

    favorites = _favorites_value(state.favorites)
    if favorites is not None:
        results = filter_by_favorites(results, favorites, favorite_keys)
        # Un dossier n'a pas d'état favori : results folders are dropped.
        folders = []

    return _sort_results(folders, results)


def _exact_folder_matches(root_node: Node, query: str) -> list[Node]:
    """Every folder whose name equals the normalized query (case- and
    space-insensitive). Used to surface the right hierarchy level: searching
    « Gunblade » returns the ``Gunblade`` folder itself, not only its skins."""
    wanted = " ".join(query.split()).casefold()
    matches: list[Node] = []

    def walk(node: Node) -> None:
        if " ".join(node.name.split()).casefold() == wanted or category_name_matches_exact(
            query, node.name
        ):
            matches.append(node)
        for sub in node.subdirs:
            walk(sub)

    for sub in root_node.subdirs:
        walk(sub)
    return matches


def _sort_results(folders: list[Node], configs: list[ConfigItem]) -> list:
    """Folder results first (canonical order), then the configurations."""
    def key(r) -> tuple:
        rank = category_rank(category_of_path(r.path) or "")
        return (0 if isinstance(r, Node) else 1, 9 if rank is None else rank, r.name.casefold())
    return sorted(list(folders) + list(configs), key=key)


# ---------------------------------------------------------------------- #
def filter_by_category(items: list[ConfigItem], category: str | None) -> list[ConfigItem]:
    """Keep only the items whose path lives under ``category`` (or all)."""
    if not category:
        return items
    return [i for i in items if category_of_path(i.path) == category]


def build_state_index(items: list[ConfigItem], sync_engine: SyncEngine) -> dict[str, SyncEntry]:
    """One SyncEngine analysis over the set, keyed by configuration name.

    Reuses the engine's own logic — no parallel activation code.
    """
    report = sync_engine.analyze(list(items), clean=False)
    return {e.name: e for e in report.entries if e.item is not None}


def filter_by_status(
    items: list[ConfigItem],
    status: str,
    index: dict[str, SyncEntry],
) -> list[ConfigItem]:
    """Filter items using the SyncEngine entries (state + issue)."""
    if not status or status == STATUS_ALL:
        return items
    out: list[ConfigItem] = []
    for item in items:
        entry = index.get(config_name(item))
        state = entry.state if entry is not None else "inactive"
        issue = entry.issue if entry is not None else "ok"
        if status == STATUS_ACTIVE and state == "active":
            out.append(item)
        elif status == STATUS_INACTIVE and state in ("inactive", "copied"):
            out.append(item)
        elif status == STATUS_MISSING and (
            issue == "missing_files" or _source_missing(item)
        ):
            out.append(item)
        elif status == STATUS_SYNC and entry is not None and entry.needs_action:
            out.append(item)
    return out


def _source_missing(item: ConfigItem) -> bool:
    """True when one of the item's own library files has disappeared."""
    if any(not p.exists() for p in item.files):
        return True
    return item.obj is not None and not item.obj.exists()


def filter_by_favorites(
    items: list[ConfigItem],
    favorites: str | None,
    favorite_keys: set[str] | None,
) -> list[ConfigItem]:
    """Keep only favourite (or non-favourite) items.

    ``favorite_keys`` is the set of favourite config keys (paths as
    strings, the cards' stable identity). Without a key set, nothing is
    guessed: ``fav`` yields an empty list, ``nofav`` keeps everything.
    """
    if not favorites or favorites == FAVORITES_ALL:
        return items
    keys = favorite_keys or set()
    if favorites == FAVORITES_ONLY:
        return [i for i in items if str(i.path) in keys]
    return [i for i in items if str(i.path) not in keys]
