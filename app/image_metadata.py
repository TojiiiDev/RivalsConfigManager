"""Image metadata (``.image.json``) handling — pure logic, no Qt.

Every card shown by the application (a category folder, a sub-folder, a
weapon, or a final configuration) can have a small sidecar file describing
its image:

    Rival Skin.json          <- the real configuration (never modified)
    Rival Skin.image.json    <- interface metadata (image association)
    Rival Skin.obj           <- real asset (never modified)

or, for a folder (category / node / folder configuration):

    Primary/
    ├── ...
    └── image.json

The sidecar only stores image information:

    {
        "version": 1,
        "type": "local" | "url",
        "source": "C:\\...\\original.png" or "https://...",
        "local_path": "image_cache/<id>.png"   # relative to the app data dir
    }

``local_path`` is used for display (the image is always copied into the
application's image cache, so it works offline and survives the original
being moved or deleted).

The identifier is derived from the **full absolute path**, so two elements
sharing a name in different folders never collide.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .config import data_dir
from .models import KIND_FOLDER, ConfigItem, Node

IMAGE_METADATA_SUFFIX = ".image.json"
METADATA_VERSION = 1

#: Any object that has a ``path`` and can be displayed as a card.
CardTarget = ConfigItem | Node


def is_image_metadata(path: Path) -> bool:
    """True for image sidecars, which are never configurations.

    Two forms exist: ``Rival Skin.image.json`` next to a single-JSON
    configuration, and ``image.json`` inside a folder (category node or
    folder configuration).
    """
    name = path.name.lower()
    return name.endswith(IMAGE_METADATA_SUFFIX) or name == "image.json"


def metadata_path_for(item: CardTarget) -> Path:
    """Return the sidecar path associated with an element.

    Folders (navigation nodes and folder configurations) store their sidecar
    *inside* the folder; file configurations use ``<name>.image.json`` next
    to the file.
    """
    if isinstance(item, Node) or item.kind == KIND_FOLDER:
        return item.path / "image.json"
    return item.path.with_name(item.path.stem + IMAGE_METADATA_SUFFIX)


def load_metadata(item: CardTarget) -> dict | None:
    """Read the sidecar. Returns ``None`` when missing or unreadable."""
    path = metadata_path_for(item)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def save_metadata(item: CardTarget, data: dict) -> None:
    """Write the sidecar atomically (version field always set)."""
    path = metadata_path_for(item)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": METADATA_VERSION, **data}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def delete_metadata(item: CardTarget) -> bool:
    """Remove the sidecar. Returns True if a file was deleted."""
    path = metadata_path_for(item)
    if not path.exists():
        return False
    try:
        path.unlink()
        return True
    except OSError:
        return False


def stable_id_for_path(path: Path) -> str:
    """Stable identifier derived from an absolute path.

    Identical across restarts, distinct between two elements that share a
    name in different folders (no cache collisions).
    """
    raw = str(Path(path).resolve())
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def stable_id(item: CardTarget) -> str:
    """Stable identifier for a configuration or a folder."""
    return stable_id_for_path(item.path)


def local_image_path(item: CardTarget) -> Path | None:
    """The cached image file from the sidecar, if it still exists."""
    meta = load_metadata(item)
    if not meta:
        return None
    local = meta.get("local_path")
    if not local:
        return None
    path = Path(local)
    if not path.is_absolute():
        path = data_dir() / path
    return path if path.is_file() else None


def effective_preview(item: CardTarget) -> Path | None:
    """Display priority: sidecar image, then the library preview, then None."""
    local = local_image_path(item)
    return local if local is not None else item.preview


def apply_metadata(node: Node) -> None:
    """Walk the tree and resolve every card's preview.

    Folders (nodes), folder configurations and file configurations all get
    their own image, independently: a category image never replaces its
    children's images. Called after a scan so cards immediately show the
    associated image.
    """
    node.preview = effective_preview(node)
    for config in node.configs:
        config.preview = effective_preview(config)
    for sub in node.subdirs:
        apply_metadata(sub)
