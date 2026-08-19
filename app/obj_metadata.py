"""OBJ metadata (``.obj.json``) handling — pure logic, no Qt.

A configuration can be associated with a 3D model (``.obj``). The real
``.obj`` file is never modified: the association lives in a small sidecar:

    Rival Skin.json          <- the real configuration (never modified)
    Rival Skin.obj           <- the real model (never modified)
    Rival Skin.obj.json      <- interface metadata (obj association)

or, for a folder configuration:

    Rival Skin/
    ├── config.json
    └── obj.json

The sidecar only stores the model association:

    {
        "version": 1,
        "type": "local",
        "source": "C:\\...\\original.obj",          # where the model came from
        "local_path": "obj_cache/<id>.obj",        # relative to the app data dir
        "file_name": "original.obj"                # original name, kept for copying
    }

``local_path`` points to a copy stored in the application's obj cache, so
the association survives the original being moved or deleted. ``file_name``
remembers the original base name so activation can place the model next to
the configuration with a sensible name.
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import data_dir
from .image_metadata import stable_id_for_path
from .models import KIND_FOLDER, ConfigItem, Node

OBJ_METADATA_SUFFIX = ".obj.json"
OBJ_METADATA_VERSION = 1

CardTarget = ConfigItem | Node


def is_obj_metadata(path: Path) -> bool:
    """True for obj sidecars, which are never configurations.

    Two forms exist: ``Rival Skin.obj.json`` next to a single-JSON
    configuration, and ``obj.json`` inside a folder configuration.
    """
    name = path.name.lower()
    return name.endswith(OBJ_METADATA_SUFFIX) or name == "obj.json"


def metadata_path_for(item: CardTarget) -> Path:
    """Return the sidecar path associated with an element."""
    if isinstance(item, Node) or item.kind == KIND_FOLDER:
        return item.path / "obj.json"
    return item.path.with_name(item.path.stem + OBJ_METADATA_SUFFIX)


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
    payload = {"version": OBJ_METADATA_VERSION, **data}
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


def stable_obj_id(item: CardTarget) -> str:
    """Stable identifier for the obj cache file name (from the full path)."""
    return stable_id_for_path(item.path)


def associated_obj(item: CardTarget) -> Path | None:
    """The cached obj file from the sidecar, if it still exists."""
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


def original_name(item: CardTarget) -> str | None:
    """The original file name of the associated obj, if recorded."""
    meta = load_metadata(item)
    if not meta:
        return None
    return meta.get("file_name") or None


def apply_obj_metadata(node: Node) -> None:
    """Walk the tree and apply manual obj associations to configs.

    A sidecar association (set with « Ajouter un OBJ ») overrides the
    auto-detection done by the scanner. The real files are never touched.
    """
    for config in node.configs:
        cached = associated_obj(config)
        name = original_name(config)
        if cached is not None:
            config.obj = cached
            config.obj_name = name or cached.name
    for sub in node.subdirs:
        apply_obj_metadata(sub)
