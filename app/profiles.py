"""User profiles — save a group of configurations and restore them later.

A :class:`Profile` captures which configurations form a setup (« Tryhard »,
« Ranked », ...). Entries reference configurations **logically** — by their
path relative to the library root — never by absolute paths, so a profile
keeps working when the library moves and can be exported without leaking
any personal data.

Storage: one JSON file per profile inside
``%APPDATA%/RivalsConfigManager/profiles/``. Export writes the same JSON
with the ``.rcmprofile`` extension (only the logical references + profile
metadata — no settings, no absolute paths, no logs, no caches); import
reads it back and validates it.

Applying a profile is done by the UI (:meth:`ProfileManager.apply` is kept
logic-only here): resolve each entry, warn about missing configurations,
then activate the present ones through the existing Fleasion mechanism,
respecting ``hot_activation_enabled`` and confirming the real state —
a profile is never reported as applied without Fleasion's confirmation.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import data_dir
from .i18n import t

#: Extension of exported profiles (1.3.0).
PROFILE_EXTENSION = ".rcmprofile"

#: Current export format version.
PROFILE_FORMAT_VERSION = 1


class ProfileError(Exception):
    """User-facing profile error with a clear message."""


@dataclass
class ProfileEntry:
    """One configuration of a profile — logical reference, never absolute."""

    name: str            # configuration display name
    rel_path: str        # path relative to the library root (posix, logical)
    category: str = ""   # canonical category key or display folder name

    def to_dict(self) -> dict:
        return {"name": self.name, "rel_path": self.rel_path, "category": self.category}

    @classmethod
    def from_dict(cls, data: dict) -> "ProfileEntry":
        return cls(
            name=str(data.get("name", "")),
            rel_path=str(data.get("rel_path", "")),
            category=str(data.get("category", "")),
        )


@dataclass
class Profile:
    """A saved group of configurations."""

    name: str
    description: str = ""
    icon: str = ""                        # optional icon key (no emoji)
    entries: list[ProfileEntry] = field(default_factory=list)
    created: float = 0.0
    updated: float = 0.0

    def to_dict(self) -> dict:
        return {
            "format": PROFILE_FORMAT_VERSION,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "created": self.created,
            "updated": self.updated,
            "entries": [e.to_dict() for e in self.entries],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Profile":
        raw_entries = data.get("entries", []) if isinstance(data, dict) else []
        entries = [
            ProfileEntry.from_dict(e)
            for e in raw_entries
            if isinstance(e, dict) and e.get("name") and e.get("rel_path")
        ]
        return cls(
            name=str(data.get("name", "")).strip(),
            description=str(data.get("description", "")),
            icon=str(data.get("icon", "")),
            entries=entries,
            created=float(data.get("created", 0.0)),
            updated=float(data.get("updated", 0.0)),
        )

    @property
    def count(self) -> int:
        return len(self.entries)

    def summary(self) -> str:
        n = self.count
        return t("profiles.count_one", count=n) if n == 1 else t("profiles.count_many", count=n)


def profiles_dir() -> Path:
    """Return (and create) the profiles directory."""
    d = data_dir() / "profiles"
    d.mkdir(parents=True, exist_ok=True)
    return d


def safe_profile_name(name: str) -> str:
    """A safe single file-name component for a profile."""
    cleaned = re.sub(r'[\\/:*?"<>|]', "", name.strip()).strip(" .")
    return cleaned or "profile"


class ProfileManager:
    """Create, list, update, delete, export and import profiles."""

    def __init__(self, directory: Path | None = None) -> None:
        self._dir = Path(directory) if directory is not None else profiles_dir()
        self._dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    def list_profiles(self) -> list[Profile]:
        """All stored profiles, sorted by name (case-insensitive)."""
        profiles: list[Profile] = []
        try:
            files = sorted(self._dir.glob("*.json"), key=lambda p: p.name.casefold())
        except OSError:
            return profiles
        for path in files:
            profile = self._read_file(path)
            if profile is not None:
                profiles.append(profile)
        return profiles

    def get(self, name: str) -> Profile | None:
        for profile in self.list_profiles():
            if profile.name == name:
                return profile
        return None

    def exists(self, name: str) -> bool:
        return self.get(name) is not None

    # ------------------------------------------------------------------ #
    def create(
        self,
        name: str,
        description: str = "",
        icon: str = "",
        entries: list[ProfileEntry] | None = None,
    ) -> Profile:
        name = name.strip()
        if not name:
            raise ProfileError(t("profiles.name_required"))
        if self.exists(name):
            raise ProfileError(t("profiles.already_exists", name=name))
        now = time.time()
        profile = Profile(
            name=name,
            description=description.strip(),
            icon=icon,
            entries=list(entries or []),
            created=now,
            updated=now,
        )
        self._write_file(profile)
        return profile

    def update(self, profile: Profile) -> None:
        profile.updated = time.time()
        self._delete_file(profile.name)
        self._write_file(profile)

    def delete(self, name: str) -> bool:
        return self._delete_file(name)

    # ------------------------------------------------------------------ #
    def export_profile(self, name: str, destination: Path) -> Path:
        """Export a profile to ``destination`` (a ``.rcmprofile`` file).

        Only the profile's own data is written — logical references, never
        absolute paths, settings or any personal file.
        """
        profile = self.get(name)
        if profile is None:
            raise ProfileError(t("profiles.not_found", name=name))
        destination = Path(destination)
        if destination.suffix.lower() != PROFILE_EXTENSION:
            destination = destination.with_suffix(PROFILE_EXTENSION)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(profile.to_dict(), indent=2), encoding="utf-8"
        )
        return destination

    def import_profile(self, source: Path) -> Profile:
        """Import a ``.rcmprofile`` file into the profiles directory.

        The file is validated first; on any problem a :class:`ProfileError`
        is raised and nothing is stored. An imported profile with an
        existing name is stored under a suffixed name (never overwritten).
        """
        source = Path(source)
        try:
            data = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ProfileError(t("profiles.import_invalid", path=source)) from exc
        profile = Profile.from_dict(data)
        if not profile.name:
            raise ProfileError(t("profiles.import_invalid", path=source))
        if self.exists(profile.name):
            profile.name = self._next_free_name(profile.name)
        profile.created = profile.updated = time.time()
        self._write_file(profile)
        return profile

    # ------------------------------------------------------------------ #
    def _path_for(self, name: str) -> Path:
        return self._dir / f"{safe_profile_name(name)}.json"

    def _read_file(self, path: Path) -> Profile | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        profile = Profile.from_dict(data)
        return profile if profile.name else None

    def _write_file(self, profile: Profile) -> None:
        path = self._path_for(profile.name)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
        tmp.replace(path)

    def _delete_file(self, name: str) -> bool:
        path = self._path_for(name)
        try:
            path.unlink()
            return True
        except OSError:
            return False

    def _next_free_name(self, name: str) -> str:
        suffix = 2
        candidate = f"{name} ({suffix})"
        while self.exists(candidate):
            suffix += 1
            candidate = f"{name} ({suffix})"
        return candidate
