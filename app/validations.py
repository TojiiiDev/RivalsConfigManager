"""User validations — a configuration « works » despite flagged dependencies.

The automatic OBJ/MP3 scanner (``app.config_analysis``) reports missing
dependencies it detects from the JSON content. Sometimes that detection is a
false positive for a specific configuration (e.g. a sound is already
integrated in Fleasion, or the reference is stale): the user can *validate*
that the configuration really works, and the app then stops treating the
flagged dependencies as blocking **for that configuration only**.

Rules (v1.3.4):

* The scanner is never modified and keeps reporting what it detects.
* A validation is a local, per-configuration confirmation. It is keyed by a
  **stable identity** (the configuration path, the same identity used by the
  favourites system — never the display name alone).
* Validating never touches the original files and never disables detection
  globally.
* A validation can always be reset (``clear_validated``).

Storage: one JSON file per user (``%APPDATA%/RivalsConfigManager/validations.json``):

    {
        "version": 1,
        "validated": {
            "<config path>": {
                "name": "Kirambit",
                "rel_path": "rivals skins/melee/katana/Kirambit",
                "at": 1724000000.0
            }
        }
    }

The key is the same ``str(item.path)`` convention used by favourites, so a
validation survives restarts and stays attached to the real configuration.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import data_dir

#: Current storage format version.
VALIDATIONS_VERSION = 1

#: File name of the validation store inside the app data folder.
VALIDATIONS_FILE = "validations.json"


@dataclass
class ValidationEntry:
    """One user validation: the configuration works despite its flagged
    dependencies."""

    name: str = ""          # display name (informational only, never the key)
    rel_path: str = ""      # path relative to the library root (informational)
    at: float = 0.0         # timestamp of the validation


class ValidationStore:
    """Persist and query user validations (local, never touches the library
    files and never modifies the global scanner)."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path is not None else data_dir() / VALIDATIONS_FILE
        self._entries: dict[str, ValidationEntry] = {}
        self._load()

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def is_validated(self, key: str) -> bool:
        """True when the configuration identified by ``key`` was validated
        by the user."""
        return key in self._entries

    def set_validated(
        self,
        key: str,
        name: str = "",
        rel_path: str = "",
    ) -> None:
        """Record the user's confirmation that the configuration works
        despite its currently flagged dependencies. Persisted immediately."""
        self._entries[key] = ValidationEntry(
            name=name,
            rel_path=rel_path,
            at=time.time(),
        )
        self._save()

    def clear_validated(self, key: str) -> bool:
        """Reset the validation of one configuration. Returns True when a
        validation was actually removed."""
        if key not in self._entries:
            return False
        del self._entries[key]
        self._save()
        return True

    def entry(self, key: str) -> ValidationEntry | None:
        return self._entries.get(key)

    def all(self) -> dict[str, ValidationEntry]:
        """Every stored validation (key -> entry)."""
        return dict(self._entries)

    def clear_all(self) -> None:
        """Drop every validation (used by tests)."""
        self._entries.clear()
        self._save()

    # ------------------------------------------------------------------ #
    def _load(self) -> None:
        """Read the store; a missing/corrupt file simply means no
        validations (never an error)."""
        if not self._path.is_file():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return
        raw = data.get("validated") if isinstance(data, dict) else None
        if not isinstance(raw, dict):
            return
        for key, value in raw.items():
            if not isinstance(key, str) or not key or not isinstance(value, dict):
                continue
            self._entries[key] = ValidationEntry(
                name=str(value.get("name", "")),
                rel_path=str(value.get("rel_path", "")),
                at=float(value.get("at", 0.0) or 0.0),
            )

    def _save(self) -> None:
        payload = {
            "version": VALIDATIONS_VERSION,
            "validated": {
                key: {
                    "name": entry.name,
                    "rel_path": entry.rel_path,
                    "at": entry.at,
                }
                for key, entry in self._entries.items()
            },
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self._path)  # atomic write
