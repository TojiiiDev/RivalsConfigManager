"""Recently opened configurations — small, bounded, persistent store.

The dedicated search page shows « Récents »: the configurations the user
recently consulted (opened) or used (activated). The list is persisted in
``%APPDATA%/RivalsConfigManager/recents.json`` and bounded to a reasonable
maximum — the store never grows unbounded.

Entries are keyed by the configuration's stable key (its path as a string,
the same identity the cards use). Only the logical identity + a display
name are kept — never file contents, never personal data.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from .config import data_dir

#: Maximum number of recents kept (oldest are dropped first).
MAX_RECENTS = 20

#: File name inside the data directory.
_RECENTS_FILE = "recents.json"


@dataclass
class RecentEntry:
    """One recently consulted configuration."""

    key: str          # stable key (config path as string)
    name: str         # display name
    timestamp: float  # last access time (monotonic-ish epoch seconds)

    def to_dict(self) -> dict:
        return {"key": self.key, "name": self.name, "timestamp": self.timestamp}

    @classmethod
    def from_dict(cls, data: dict) -> "RecentEntry":
        return cls(
            key=str(data.get("key", "")),
            name=str(data.get("name", "")),
            timestamp=float(data.get("timestamp", 0.0)),
        )


def recents_file() -> Path:
    return data_dir() / _RECENTS_FILE


class RecentsStore:
    """Persist and query the recent-configurations list (bounded)."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path is not None else recents_file()
        self._entries: list[RecentEntry] = []
        self._load()

    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            raw = data.get("recents", []) if isinstance(data, dict) else data
        except (OSError, json.JSONDecodeError, UnicodeDecodeError, TypeError):
            raw = []
        entries: list[RecentEntry] = []
        seen: set[str] = set()
        for item in raw if isinstance(raw, list) else []:
            if not isinstance(item, dict):
                continue
            entry = RecentEntry.from_dict(item)
            if not entry.key or entry.key in seen:
                continue
            seen.add(entry.key)
            entries.append(entry)
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        self._entries = entries[:MAX_RECENTS]

    def _save(self) -> None:
        payload = {
            "recents": [e.to_dict() for e in self._entries],
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    # ------------------------------------------------------------------ #
    def record(self, key: str, name: str, timestamp: float | None = None) -> None:
        """Record an access to a configuration (moves it to the front)."""
        if not key:
            return
        now = timestamp if timestamp is not None else time.time()
        self._entries = [e for e in self._entries if e.key != key]
        self._entries.insert(0, RecentEntry(key=key, name=name, timestamp=now))
        del self._entries[MAX_RECENTS:]
        self._save()

    def entries(self) -> list[RecentEntry]:
        """The recents, most recent first."""
        return list(self._entries)

    def clear(self) -> None:
        self._entries = []
        self._save()

    def __len__(self) -> int:
        return len(self._entries)
