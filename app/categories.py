"""Canonical weapon categories and their strict display order.

The application always shows and sorts the four weapon categories in the
same order, everywhere (display, selectors, filters, internal sorting):

    1. Primaire    (primary)
    2. Secondaire  (secondary)
    3. Mêlée       (melee)
    4. Utilitaire  (utility)

Everything else (charms, emotes, fast flags, textures, ...) comes after,
alphabetically. The mapping is name-based and case-insensitive, so both the
English folder names (Primary, Secondary, Melee, Utility) and their French
equivalents are recognised.

Nothing in this module moves files: it only orders what is displayed, so
existing configurations and sidecars keep working untouched.
"""

from __future__ import annotations

from pathlib import Path

from .models import ConfigItem, Node

#: Canonical category keys, in the strict display order.
CATEGORY_KEYS = ("primary", "secondary", "melee", "utility")

#: French display labels for the canonical categories.
CATEGORY_LABELS = {
    "primary": "Primaire",
    "secondary": "Secondaire",
    "melee": "Mêlée",
    "utility": "Utilitaire",
}

#: Canonical English folder names used when the application creates
#: category folders on disk (e.g. when installing an imported mod).
CATEGORY_FOLDER_NAMES = {
    "primary": "Primary",
    "secondary": "Secondary",
    "melee": "Melee",
    "utility": "Utility",
}


def folder_name_for(key: str) -> str:
    """The folder name used on disk for a canonical category key."""
    return CATEGORY_FOLDER_NAMES.get(key, key)


def safe_folder_name(text: str) -> str:
    """A safe single folder-name component: separators and forbidden
    characters are removed, leading/trailing dots and spaces are trimmed.
    Returns ``""`` when nothing usable remains."""
    return "".join(c for c in text.strip() if c not in '/\\:*?"<>|').strip(" .")


def ensure_weapon_folder(
    library_root,
    category: str,
    weapon_name: str,
    parent: Path | None = None,
) -> Path | None:
    """Create (if needed) the weapon folder ``<parent>/<Arme>``.

    ``parent`` is the **actual category folder** on disk (resolved from the
    current navigation context, e.g. ``Rivals configs/Skins/Primary``); when
    it is given it wins, so a weapon is never created at a guessed root
    location. Without ``parent`` the folder is ``<library>/<Catégorie>``
    (the canonical root-level fallback). Returns the folder path, or
    ``None`` when the name is unusable or the folder cannot be created.
    Creating an existing folder is a no-op (never duplicated).
    """
    name = safe_folder_name(weapon_name)
    if not name:
        return None
    base = Path(parent) if parent is not None else Path(library_root) / folder_name_for(category)
    target = base / name
    try:
        target.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    return target


def category_folder_in_path(library_root, path) -> Path | None:
    """The real category folder inside a path, or ``None``.

    Walks ``path`` (relative to ``library_root``) and returns the folder of
    the **deepest** part that is a weapon category (Primary / Secondary /
    Melee / Utility, EN or FR aliases). This is how « Ajouter une arme »
    finds the exact parent: browsing ``Skins/Primary`` or
    ``Skins/Primary/Assault Rifle`` both resolve to the real ``Skins/Primary``
    folder on disk. Returns ``None`` when the path contains no category
    folder — the caller must not guess.
    """
    root = Path(library_root)
    current = root
    try:
        rel = Path(path).resolve().relative_to(root.resolve())
    except ValueError:
        return None
    found: Path | None = None
    for part in rel.parts:
        current = current / part
        if category_rank(part) is not None:
            found = current
    return found


def resolve_category_folder(library_root, category: str) -> Path | None:
    """The real on-disk folder of a canonical category key, or ``None``.

    Canonical keys (primary / secondary / melee / utility) may live
    anywhere in the library — the real library organises them under
    ``rivals skins/`` (``rivals skins/primary``), other libraries at the
    root. This searches the library tree and returns the **existing**
    category folder, preferring a nested one (the user's real organisation)
    over the root-level fallback the installer would create. Returns
    ``None`` when no such folder exists — the caller then falls back to the
    canonical root-level folder (``<library>/Primary``), created on demand.

    Non-canonical categories (``Charms``, ``rivals skins``, ...) are
    top-level folders by definition: ``None`` is returned and the caller
    uses ``<library>/<name>`` as today.
    """
    if category not in CATEGORY_KEYS:
        return None
    root = Path(library_root)
    if not root.is_dir():
        return None

    def matches(folder: Path) -> bool:
        return category_rank(folder.name) is not None and (
            CATEGORY_KEYS[category_rank(folder.name)] == category
        )

    # Pass 1 — nested category folders (the user's real organisation,
    # e.g. ``rivals skins/primary``), depth-first, deterministic order.
    try:
        top_level = sorted(
            (p for p in root.iterdir() if p.is_dir() and not p.name.startswith(".")),
            key=lambda p: p.name.casefold(),
        )
    except OSError:
        top_level = []
    for top in top_level:
        if matches(top):
            continue  # root-level match: kept for pass 2
        found = _find_category_in(top, category, depth=0, max_depth=8)
        if found is not None:
            return found
    # Pass 2 — root-level canonical folder (``<library>/Primary``), the
    # layout the installer itself creates.
    for top in top_level:
        if matches(top):
            return top
    return None


def _find_category_in(
    folder: Path, category: str, depth: int, max_depth: int
) -> Path | None:
    """Depth-first search of a category folder inside ``folder`` (folders
    only, bounded depth, deterministic sorted order)."""
    if depth >= max_depth:
        return None
    try:
        children = sorted(
            (p for p in folder.iterdir() if p.is_dir() and not p.name.startswith(".")),
            key=lambda p: p.name.casefold(),
        )
    except OSError:
        return None
    for child in children:
        if category_rank(child.name) is not None and (
            CATEGORY_KEYS[category_rank(child.name)] == category
        ):
            return child
    for child in children:
        found = _find_category_in(child, category, depth + 1, max_depth)
        if found is not None:
            return found
    return None


#: Folder-name variants -> canonical key (compared case-insensitively).
_CATEGORY_ALIASES = {
    "primary": "primary",
    "primaire": "primary",
    "prim": "primary",
    "secondary": "secondary",
    "secondaire": "secondary",
    "sec": "secondary",
    "melee": "melee",
    "mêlée": "melee",
    "utility": "utility",
    "utilitaire": "utility",
    "util": "utility",
}


def ordered_categories() -> list[str]:
    """The canonical category keys, in strict display order."""
    return list(CATEGORY_KEYS)


def import_categories(library_root=None) -> list[str]:
    """All categories offered by the import picker, built **dynamically**.

    The canonical weapon categories always come first, in canonical order
    (Primary → Secondary → Melee → Utility — they are valid destinations
    even before they exist on disk, the installer creates them). Then the
    library's **actual top-level folders** are appended, alphabetically:
    Charms, Skins, Textures, any custom folder — including empty folders.

    Nothing here is hard-coded: add a folder to the library and it appears
    in the list without touching the code. Top-level folders whose name is
    one of the canonical English folder names (Primary, Secondary, ...) are
    skipped — the canonical entry already targets that exact destination.
    """
    categories = list(CATEGORY_KEYS)
    if library_root is None:
        return categories
    try:
        entries = sorted(Path(library_root).iterdir(), key=lambda p: p.name.casefold())
    except OSError:
        return categories
    reserved = {folder_name_for(key).casefold() for key in CATEGORY_KEYS}
    for entry in entries:
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if entry.name.casefold() in reserved:
            continue
        categories.append(entry.name)
    return categories


def display_label(key: str) -> str:
    """Display label of a canonical category key, in the current language.

    Canonical keys (primary, secondary, melee, utility) are translated;
    anything else (a real library folder such as ``Charms``) is returned
    unchanged — user folder names are never translated.
    """
    from .i18n import t

    if key in CATEGORY_LABELS:
        return t(f"category.{key}")
    return key


def category_rank(name: str) -> int | None:
    """The canonical rank (0-3) of a category folder name, or ``None`` when
    the name is not one of the weapon categories."""
    key = _CATEGORY_ALIASES.get(name.strip().casefold())
    if key is None:
        return None
    return CATEGORY_KEYS.index(key)


def category_of_path(path) -> str | None:
    """The canonical category implied by the folder names of a path.

    The deepest category part wins. Returns ``None`` when the path contains
    no category folder.
    """
    key: str | None = None
    for part in Path(path).parts:
        found = _CATEGORY_ALIASES.get(part.casefold())
        if found is not None:
            key = found
    return key


def destination_categories(library_root) -> list[tuple[str, Path | None]]:
    """Root categories for the progressive destination picker.

    Returns ``(category_key_or_folder_name, resolved_folder_or_None)``
    pairs: the canonical weapon categories first — each resolved to its
    **real** on-disk folder (``rivals skins/primary`` in the real library),
    or ``None`` when it does not exist yet (the installer then creates the
    canonical root-level folder) — followed by the library's top-level
    folders that are real categories. Pure category containers such as
    ``rivals skins`` (whose content IS the weapon categories) are skipped:
    their categories are already listed. Nothing is hard-coded: a new
    top-level folder appears automatically.
    """
    root = Path(library_root)
    entries: list[tuple[str, Path | None]] = []
    for key in CATEGORY_KEYS:
        entries.append((key, resolve_category_folder(root, key)))
    try:
        top_level = sorted(
            (
                p
                for p in root.iterdir()
                if p.is_dir() and not p.name.startswith(".")
            ),
            key=lambda p: p.name.casefold(),
        )
    except OSError:
        return entries
    reserved = {folder_name_for(key).casefold() for key in CATEGORY_KEYS}
    for folder in top_level:
        name = folder.name
        if name.casefold() in reserved:
            continue
        if _is_category_container(folder):
            continue
        entries.append((name, folder))
    return entries


def _is_category_container(folder: Path) -> bool:
    """A top-level folder whose content is the weapon categories themselves
    (e.g. ``rivals skins`` containing primary / Secondary / Melee / utility)
    and no configuration of its own — it is not a category, its subfolders
    are."""
    try:
        children = list(folder.iterdir())
    except OSError:
        return False
    has_category = False
    has_config = False
    for child in children:
        if child.is_dir():
            if category_rank(child.name) is not None:
                has_category = True
        elif child.suffix.lower() == ".json" and not _is_preview_sidecar(child.name):
            has_config = True
    return has_category and not has_config


def _is_preview_sidecar(name: str) -> bool:
    """Preview/metadata sidecars (``image.json``, ``*.image.json``,
    ``*.obj.json``) are not configurations."""
    lower = name.lower()
    return (
        lower == "image.json"
        or lower.endswith(".image.json")
        or lower.endswith(".obj.json")
    )


def category_weapon_folders(category_folder: Path | None) -> list[str]:
    """The weapon folder names directly inside a category folder, sorted."""
    if category_folder is None or not category_folder.is_dir():
        return []
    try:
        return sorted(
            (
                p.name
                for p in category_folder.iterdir()
                if p.is_dir() and not p.name.startswith(".")
            ),
            key=str.casefold,
        )
    except OSError:
        return []


def category_name_matches_exact(query: str, folder_name: str) -> bool:
    """True when a normalized query **equals** the folder name or one of
    its category aliases (exact, not partial). Used by the hierarchical
    search so « primaire » surfaces the ``Primary`` folder just like
    « primary » does."""
    key = _CATEGORY_ALIASES.get(folder_name.strip().casefold())
    if key is None:
        return False
    q = _normalize(query)
    if not q:
        return False
    if q == _normalize(folder_name):
        return True
    return any(
        q == _normalize(alias)
        for alias, alias_key in _CATEGORY_ALIASES.items()
        if alias_key == key
    )


def category_matches_query(query: str, folder_name: str) -> bool:
    """True when a normalized query matches a category folder, either by its
    own name or by any of its alias variants (EN/FR, case-insensitive).

    This makes « primary » and « primaire » both filter the Primary
    category, whatever the language of the folder on disk.
    """
    key = _CATEGORY_ALIASES.get(folder_name.strip().casefold())
    if key is None:
        return False
    q = _normalize(query)
    if not q:
        return False
    names = {key}
    for alias, alias_key in _CATEGORY_ALIASES.items():
        if alias_key == key:
            names.add(alias)
    return any(q in name for name in names)


def sort_nodes(nodes: list[Node]) -> list[Node]:
    """Stable sort: canonical categories first (in order), then the rest
    alphabetically."""
    return sorted(nodes, key=_node_key)


def sort_configs(configs: list[ConfigItem]) -> list[ConfigItem]:
    """Stable alphabetical sort of configurations."""
    return sorted(configs, key=lambda c: c.name.casefold())


def sort_search_results(results: list[ConfigItem]) -> list[ConfigItem]:
    """Search results: the item's category first (canonical order), then
    the name — primaire results come before charm results."""
    return sorted(results, key=_result_key)


# ---------------------------------------------------------------------- #
def _normalize(text: str) -> str:
    """Trim and collapse inner whitespace, lower-case — for matching."""
    return " ".join(text.split()).casefold()


def _node_key(node: Node) -> tuple:
    rank = category_rank(node.name)
    if rank is None:
        return (1, 0, node.name.casefold())
    return (0, rank, node.name.casefold())


def _result_key(item: ConfigItem) -> tuple:
    rank = category_rank(category_of_path(item.path) or "")
    return (9 if rank is None else rank, item.name.casefold())
