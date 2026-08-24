"""Data model produced by the library scanner.

The library is scanned into a tree of :class:`Node` objects. Every folder
either contains sub-folders (navigation) or configuration items (leaf
content). This keeps the whole application generic: nothing is hard-coded
about weapons, skins, charms, etc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

KIND_FILE = "file"
KIND_FOLDER = "folder"


@dataclass
class ConfigItem:
    """A selectable configuration — either a single file or a folder."""

    name: str
    path: Path                       # path of the file or the folder
    kind: str                        # KIND_FILE or KIND_FOLDER
    files: list[Path] = field(default_factory=list)       # files to copy
    json_files: list[Path] = field(default_factory=list)  # json files among them
    preview: Path | None = None      # preview image if one was found
    # -- OBJ support ------------------------------ #
    obj: Path | None = None          # first associated obj (backward-compat)
    obj_name: str | None = None      # first obj destination name (backward-compat)
    # v2 multi-OBJ: extra objs beyond the first --------------------------- #
    _extra_objs: list[Path] = field(default_factory=list, repr=False)
    _extra_names: list[str] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------------ #
    # Multi-OBJ properties
    # ------------------------------------------------------------------ #
    @property
    def objs(self) -> list[Path]:
        """All associated OBJ file paths (cache paths or library paths)."""
        base = [self.obj] if self.obj is not None else []
        return base + self._extra_objs

    @property
    def obj_names(self) -> list[str]:
        """Destination names for every associated OBJ."""
        base = [self.obj_name] if self.obj_name is not None else []
        return base + self._extra_names

    def add_obj(self, path: Path, name: str) -> None:
        """Append a new OBJ (never replaces existing ones)."""
        if self.obj is None:
            self.obj = path
            self.obj_name = name
        else:
            self._extra_objs.append(path)
            self._extra_names.append(name)

    def remove_obj_at(self, index: int) -> None:
        """Remove one OBJ. Index 0 removes the first, shifting extras down."""
        all_objs = self.objs
        all_names = self.obj_names
        if not (0 <= index < len(all_objs)):
            return
        del all_objs[index]
        del all_names[index]
        # Rebuild from the remaining lists.
        self.obj = all_objs[0] if all_objs else None
        self.obj_name = all_names[0] if all_names else None
        self._extra_objs = all_objs[1:]
        self._extra_names = all_names[1:]

    def replace_obj_at(self, index: int, path: Path, name: str) -> None:
        """Replace one OBJ at the given index."""
        if index == 0:
            self.obj = path
            self.obj_name = name
        else:
            extra_idx = index - 1
            if 0 <= extra_idx < len(self._extra_objs):
                self._extra_objs[extra_idx] = path
                self._extra_names[extra_idx] = name

    def set_obj_list(self, paths: list[Path], names: list[str]) -> None:
        """Replace the entire OBJ list (used by apply_obj_metadata)."""
        if not paths:
            self.obj = None
            self.obj_name = None
            self._extra_objs.clear()
            self._extra_names.clear()
        else:
            self.obj = paths[0]
            self.obj_name = names[0] if names else paths[0].name
            self._extra_objs = paths[1:]
            self._extra_names = names[1:]

    @property
    def is_folder(self) -> bool:
        return self.kind == KIND_FOLDER


@dataclass
class Node:
    """A folder inside the library."""

    name: str
    path: Path
    subdirs: list["Node"] = field(default_factory=list)
    configs: list[ConfigItem] = field(default_factory=list)
    preview: Path | None = None

    def all_configs(self) -> list[ConfigItem]:
        """Config items directly inside this folder."""
        return list(self.configs)

    def total_items(self) -> int:
        """Number of directly visible entries (sub-folders + configs)."""
        return len(self.subdirs) + len(self.configs)
