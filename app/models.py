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
    obj: Path | None = None          # associated .obj model (display + copy source)
    obj_name: str | None = None      # destination file name for the obj when copying

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
