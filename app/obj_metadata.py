"""OBJ metadata (``.obj.json``) handling — pure logic, no Qt.

A configuration can be associated with several 3D models (``.obj``). The
real ``.obj`` files are never modified: the associations live in a small
sidecar:

    Rival Skin.json          <- the real configuration (never modified)
    Rival Skin.obj           <- the real model (never modified)
    Rival Skin.obj.json      <- interface metadata (obj associations)

or, for a folder configuration:

    Rival Skin/
    ├── config.json
    └── obj.json

The sidecar stores a list of model associations (v2):

    {
        "version": 2,
        "objs": [
            {
                "type": "local",
                "source": "C:\\...\\original.obj",
                "local_path": "obj_cache/<id>_0.obj",
                "file_name": "original.obj"
            },
            ...
        ]
    }

Old v1 format (single OBJ) is auto-migrated on read:

    {
        "version": 1,
        "type": "local",
        "source": "C:\\...\\original.obj",
        "local_path": "obj_cache/<id>.obj",
        "file_name": "original.obj"
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
OBJ_METADATA_VERSION = 2

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
    """Read the sidecar. Returns ``None`` when missing or unreadable.

    Auto-migrates v1 (single OBJ) to v2 (list of OBJs) in memory.
    """
    path = metadata_path_for(item)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return _migrate(data) if isinstance(data, dict) else None
    except (json.JSONDecodeError, OSError):
        return None


def _migrate(data: dict) -> dict | None:
    """Ensure the metadata is in v2 format (list-based)."""
    if "objs" in data and isinstance(data["objs"], list):
        data.setdefault("version", OBJ_METADATA_VERSION)
        return data
    # v1 -> v2: wrap the single entry in a list.
    if isinstance(data.get("local_path"), str):
        return {
            "version": OBJ_METADATA_VERSION,
            "objs": [
                {
                    "type": data.get("type", "local"),
                    "source": data.get("source", ""),
                    "local_path": data["local_path"],
                    "file_name": data.get("file_name", ""),
                }
            ],
        }
    return data


def save_metadata(item: CardTarget, data: dict) -> None:
    """Write the sidecar atomically (version field always set).

    ``data`` must contain an ``"objs"`` list (v2 format).
    """
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
    """The first cached obj file from the sidecar, if it still exists.

    Backward-compatible: returns the first OBJ only. For the full list use
    :func:`associated_objs`.
    """
    meta = load_metadata(item)
    if not meta:
        return None
    objs = meta.get("objs")
    if isinstance(objs, list) and objs:
        local = objs[0].get("local_path") if isinstance(objs[0], dict) else None
        if local:
            path = Path(local)
            if not path.is_absolute():
                path = data_dir() / path
            return path if path.is_file() else None
    return None


def associated_objs(item: CardTarget) -> list[Path]:
    """All cached obj files from the sidecar that still exist."""
    meta = load_metadata(item)
    if not meta:
        return []
    result: list[Path] = []
    objs = meta.get("objs")
    if isinstance(objs, list):
        for entry in objs:
            if not isinstance(entry, dict):
                continue
            local = entry.get("local_path")
            if not local:
                continue
            path = Path(local)
            if not path.is_absolute():
                path = data_dir() / path
            if path.is_file():
                result.append(path)
    return result


def associated_obj_names(item: CardTarget) -> list[str]:
    """Destination names of all associated OBJs, in order."""
    meta = load_metadata(item)
    if not meta:
        return []
    objs = meta.get("objs")
    if isinstance(objs, list):
        return [
            (entry.get("file_name") or "") if isinstance(entry, dict) else ""
            for entry in objs
        ]
    return []


def original_name(item: CardTarget) -> str | None:
    """The original file name of the first associated obj, if recorded.

    Backward-compatible; use :func:`associated_obj_names` for the full list.
    """
    names = associated_obj_names(item)
    return names[0] if names else None


def add_obj_metadata(item: CardTarget, cache_path: Path, source: Path) -> None:
    """Append a new OBJ entry to the sidecar (never overwrites)."""
    meta = load_metadata(item)
    objs = meta.get("objs") if meta and isinstance(meta.get("objs"), list) else []
    # Build a relative path for portability.
    try:
        rel = cache_path.relative_to(data_dir())
    except ValueError:
        rel = cache_path
    objs.append({
        "type": "local",
        "source": str(source),
        "local_path": rel.as_posix() if isinstance(rel, Path) else str(cache_path),
        "file_name": source.name,
    })
    save_metadata(item, {"objs": objs})


def remove_obj_metadata_at(item: CardTarget, index: int) -> bool:
    """Remove one OBJ entry at the given index. Returns True when a file
    was removed from the cache."""
    meta = load_metadata(item)
    objs = meta.get("objs") if meta and isinstance(meta.get("objs"), list) else []
    if not (0 <= index < len(objs)):
        return False
    removed_entry = objs.pop(index)
    removed_file = False
    if isinstance(removed_entry, dict):
        local = removed_entry.get("local_path")
        if local:
            path = Path(local)
            if not path.is_absolute():
                path = data_dir() / path
            try:
                if path.is_file():
                    path.unlink()
                    removed_file = True
            except OSError:
                pass
    if objs:
        save_metadata(item, {"objs": objs})
    else:
        delete_metadata(item)
    return removed_file


def replace_obj_metadata_at(item: CardTarget, index: int, cache_path: Path, source: Path) -> bool:
    """Replace one OBJ entry at the given index. Returns True on success.

    Does NOT touch cache files — the caller (:func:`ObjManager.replace_one`)
    already handles the file copy.
    """
    meta = load_metadata(item)
    objs = meta.get("objs") if meta and isinstance(meta.get("objs"), list) else []
    if not (0 <= index < len(objs)):
        return False
    try:
        rel = cache_path.relative_to(data_dir())
    except ValueError:
        rel = cache_path
    objs[index] = {
        "type": "local",
        "source": str(source),
        "local_path": rel.as_posix() if isinstance(rel, Path) else str(cache_path),
        "file_name": source.name,
    }
    save_metadata(item, {"objs": objs})
    return True


def apply_obj_metadata(node: Node) -> None:
    """Walk the tree and apply manual obj associations to configs.

    A sidecar association (set with « Ajouter un OBJ ») overrides the
    auto-detection done by the scanner. The real files are never touched.
    Multiple OBJs are supported: every cached OBJ from the sidecar is
    exposed through ``config.objs``.
    """
    for config in node.configs:
        cached_list = associated_objs(config)
        names_list = associated_obj_names(config)
        if cached_list:
            config.set_obj_list(cached_list, names_list)
    for sub in node.subdirs:
        apply_obj_metadata(sub)
