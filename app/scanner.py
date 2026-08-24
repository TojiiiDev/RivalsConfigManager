"""Library scanner.

Walks the user's "Rivals Configs" library folder and builds a generic tree
(:class:`app.models.Node`). Nothing about weapons, skins, charms or emotes
is hard-coded: add a folder or a JSON file to the library and it shows up
automatically.

Rules used to decide what is a "configuration":

* A folder containing **two or more JSON files** is a container: each JSON
  file inside becomes its own configuration (the common case for weapon
  folders holding several skins).
* A folder containing **a single JSON plus other files** (meshes, preview
  images, ...) is itself one configuration: every file inside is copied.
* A JSON file found directly in a folder is always a configuration.
* Folders containing sub-folders — and empty folders (e.g. a weapon
  created with « Ajouter une arme ») — are navigation nodes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .categories import category_matches_query
from .i18n import t
from .image_metadata import apply_metadata, is_image_metadata
from .json_validator import dependency_files
from .models import KIND_FILE, KIND_FOLDER, ConfigItem, Node
from .obj_metadata import apply_obj_metadata, is_obj_metadata

#: Preview file names, checked in priority order (case-insensitive).
PREVIEW_NAMES = (
    "preview",
    "thumbnail",
    "thumb",
    "cover",
    "image",
    "icon",
    "apercu",
    "aperçu",
    "screenshot",
)

PREVIEW_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")


@dataclass
class ScanResult:
    """Outcome of a library scan."""

    ok: bool
    node: Node | None = None
    errors: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.errors is None:
            self.errors = []


def find_preview(folder: Path) -> Path | None:
    """Look for a preview image inside ``folder``.

    Priority is given to well-known names (preview.png, thumbnail.jpg, ...).
    If none matches, a single image file present in the folder is used.
    """
    try:
        files = [p for p in folder.iterdir() if p.is_file()]
    except OSError:
        return None

    images = [p for p in files if p.suffix.lower() in PREVIEW_EXTENSIONS]
    if not images:
        return None

    for name in PREVIEW_NAMES:
        for img in images:
            if img.stem.lower() == name:
                return img
    if len(images) == 1:
        return images[0]
    return None


def _is_sidecar(path: Path) -> bool:
    """True for interface sidecars (image or obj), never real configs."""
    return is_image_metadata(path) or is_obj_metadata(path)


def _stem_obj(json_path: Path) -> Path | None:
    """The ``.obj`` sharing the JSON's stem in the same folder, if any.

    ``Skin.json`` + ``Skin.obj`` is a deterministic, unambiguous relation
    (exact name match); we never guess from a partial name when several
    files could match.
    """
    candidate = json_path.parent / f"{json_path.stem}.obj"
    return candidate if candidate.is_file() else None


def _make_file_config(json_path: Path) -> ConfigItem:
    """A single JSON file is a configuration."""
    folder = json_path.parent
    deps = dependency_files(json_path, folder)
    files = [json_path]
    files.extend(deps)

    # ``Skin.json`` + ``Skin.obj``: the model belongs to the config (exact
    # name match, never a guess).
    obj = _stem_obj(json_path)
    if obj is not None and obj not in files:
        files.append(obj)

    # A single .obj referenced by the JSON content is also a reliable
    # association (the JSON explicitly names it and the file exists next to
    # it). With several, they are all included.
    if obj is None:
        dep_objs = [d for d in deps if d.suffix.lower() == ".obj"]
        if dep_objs:
            obj = dep_objs[0]
            for dep_obj in dep_objs[1:]:
                files.append(dep_obj)
    obj_name = obj.name if obj else None

    return ConfigItem(
        name=json_path.stem,
        path=json_path,
        kind=KIND_FILE,
        files=files,
        json_files=[json_path],
        preview=find_preview(folder),
        obj=obj,
        obj_name=obj_name,
    )


def _make_folder_config(folder: Path) -> ConfigItem:
    """A folder whose whole content is one configuration."""
    try:
        files = sorted(
            (p for p in folder.iterdir() if p.is_file() and not _is_sidecar(p)),
            key=lambda p: p.name.lower(),
        )
    except OSError:
        files = []
    jsons = [p for p in files if p.suffix.lower() == ".json"]

    # A folder config owns its models: they are copied with it. The first
    # obj (if any) is the « primary » association; all are copied.
    objs = [p for p in files if p.suffix.lower() == ".obj"]

    item = ConfigItem(
        name=folder.name,
        path=folder,
        kind=KIND_FOLDER,
        files=files,
        json_files=jsons,
        preview=find_preview(folder),
    )
    for o in objs:
        item.add_obj(o, o.name)
    return item


def _json_container_node(folder: Path, jsons: list[Path]) -> Node:
    """Build a navigation node whose configurations are the folder's JSONs."""
    sub = Node(name=folder.name, path=folder, preview=find_preview(folder))
    for j in sorted(jsons, key=lambda p: p.name.lower()):
        sub.configs.append(_make_file_config(j))
    return sub


def _scan_dir(path: Path) -> Node:
    node = Node(name=path.name, path=path, preview=find_preview(path))

    try:
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
    except OSError:
        return node

    for entry in entries:
        if entry.is_dir():
            try:
                child_files = [p for p in entry.iterdir() if p.is_file()]
                child_dirs = [p for p in entry.iterdir() if p.is_dir()]
            except OSError:
                child_files, child_dirs = [], []
            if child_dirs:
                node.subdirs.append(_scan_dir(entry))
            elif child_files:
                # Sidecar files (image / obj) are invisible to the
                # classifier: they neither count as JSON configs nor as
                # companion files.
                jsons = [
                    p for p in child_files if p.suffix.lower() == ".json" and not _is_sidecar(p)
                ]
                non_jsons = [p for p in child_files if p.suffix.lower() != ".json"]
                if jsons and not non_jsons:
                    # Pure-JSON folder (weapon -> skins, skybox pack ->
                    # skyboxes, ...): keep the hierarchy, each JSON is a
                    # configuration inside it.
                    node.subdirs.append(_json_container_node(entry, jsons))
                elif len(jsons) >= 2:
                    # JSONs plus meshes/previews: still a container; the
                    # meshes are resolved as dependencies when a JSON is
                    # activated.
                    node.subdirs.append(_json_container_node(entry, jsons))
                elif jsons:
                    # Exactly one JSON with companion files: the whole
                    # folder is one configuration (config.json + preview,
                    # skin + meshes, ...).
                    node.configs.append(_make_folder_config(entry))
                else:
                    # No JSON at all: the folder is one configuration.
                    node.configs.append(_make_folder_config(entry))
            else:
                # Empty folder (weapon created with « Ajouter une arme »,
                # ...): a navigation node with no items yet, so the new
                # weapon is visible immediately and can receive mods.
                node.subdirs.append(_scan_dir(entry))
        elif entry.is_file() and entry.suffix.lower() == ".json" and not _is_sidecar(entry):
            node.configs.append(_make_file_config(entry))

    return node


def validate_library_root(root: Path) -> list[str]:
    """Check a library folder before scanning.

    Returns a list of user-facing error messages (empty = valid). This is
    the single validation entry point used by the UI: the folder must exist,
    be a real directory and be readable. Nothing is scanned here.
    """
    errors: list[str] = []
    if not root.exists():
        errors.append(t("scanner.library_not_found", root=root))
        return errors
    if not root.is_dir():
        errors.append(t("scanner.not_a_folder", root=root))
        return errors
    try:
        any(True for _ in root.iterdir())  # an empty folder is valid
    except PermissionError:
        errors.append(t("scanner.permission_denied", root=root))
        return errors
    except OSError as exc:
        errors.append(
            t("scanner.read_failed", root=root, detail=exc.strerror or exc)
        )
        return errors
    return errors


def scan_library(root: Path) -> ScanResult:
    """Scan a library folder and return its tree."""
    errors = validate_library_root(root)
    if errors:
        return ScanResult(ok=False, errors=errors)

    node = _scan_dir(root)
    # Resolve each card's image (sidecar first, then library preview) so
    # cards show the associated image immediately.
    apply_metadata(node)
    # Resolve manual obj associations (sidecar) over auto-detection.
    apply_obj_metadata(node)
    return ScanResult(ok=True, node=node, errors=errors)


def find_node(node: Node, path: Path) -> Node | None:
    """Find a node by its folder path in a freshly scanned tree."""
    if node.path == path:
        return node
    for sub in node.subdirs:
        found = find_node(sub, path)
        if found is not None:
            return found
    return None


def find_config(node: Node, path: Path) -> ConfigItem | None:
    """Find a configuration by its path in a freshly scanned tree."""
    for config in node.configs:
        if config.path == path:
            return config
    for sub in node.subdirs:
        found = find_config(sub, path)
        if found is not None:
            return found
    return None


def _normalized(text: str) -> str:
    """Trim and collapse inner whitespace, lower-case — for matching."""
    return " ".join(text.split()).casefold()


def _matches(query: str, *names: str) -> bool:
    q = _normalized(query)
    return any(q in _normalized(name) for name in names)


def _category_hit(query: str, ancestors: list[str]) -> bool:
    """True when the query matches a category ancestor via its aliases
    (EN/FR): « primaire » matches the Primary folder, « melee » too."""
    return any(category_matches_query(query, name) for name in ancestors)


def search_library(node: Node, query: str, max_results: int = 60) -> list[ConfigItem]:
    """Search the whole tree.

    Matches configuration names as well as the names of every ancestor
    folder (category, weapon type, weapon). Returns a flat list of matching
    configurations, limited to ``max_results``.
    """
    query = query.strip()
    if not query:
        return []
    results: list[ConfigItem] = []
    seen: set[str] = set()

    def walk(current: Node, ancestors: list[str]) -> None:
        for config in current.configs:
            if _matches(query, config.name, *ancestors) or _category_hit(query, ancestors):
                key = str(config.path).lower()
                if key not in seen:
                    seen.add(key)
                    results.append(config)
        for sub in current.subdirs:
            walk(sub, ancestors + [sub.name])

    walk(node, [node.name])
    return results[:max_results]
