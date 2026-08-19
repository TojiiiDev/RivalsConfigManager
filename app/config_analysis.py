"""Configuration dependency analysis: OBJ meshes and MP3 sounds.

Answers two questions about a JSON configuration:

* does it need a local ``.obj`` mesh, and is that mesh present?
* does it need a local ``.mp3`` sound, and is that sound present?

Used by the configuration view ("Dépendances" block).

Detection method — derived from inspecting the real library (360+ JSONs):

* Configurations reference their assets through ``replacement_rules``
  entries. A rule is a **local** dependency when it is *active* (its
  ``enabled`` is not ``False``) and carries a string that **ends with**
  ``.obj`` / ``.mp3`` (case-insensitive — the real library has a
  ``Keylaws sound 1.MP3``) and is **not** a URL: ``Pixelboddy.obj``,
  ``C:/mesh/Keylaws sound 1.MP3``, ``Potion satchel tube thingy.obj``.
  The referenced file name is the part after the last ``/`` or ``\\``.
* Only the ``replacement_rules`` array is scanned (recursively — rules
  nest through ``children``): the real format puts every local reference
  there. Strings anywhere else (sidecar metadata, descriptions, names,
  ``with_id`` asset references) are **never** interpreted as a dependency:
  a file's absence is never the proof that it is required, and a
  ``.obj``/``.mp3``-looking string outside the rules cannot create a
  requirement.
* A **full URL** (``https://…``) is a *remote* asset downloaded by
  Fleasion at activation time: it needs **no local file** and is ignored
  (the real library has hundreds of OBJ/MP3 URL references that must not
  be flagged).
* A rule whose ``enabled`` is ``False`` is ignored: Fleasion skips it at
  activation, so a stale ``local_path`` on a disabled rule never creates a
  requirement (this is what wrongly flagged some configs before).
* A local reference is "present" when that file exists **next to the JSON**
  in the library — exactly the convention used by the scanner and by
  :func:`app.json_validator.dependency_files`. Remote URLs and stale
  absolute paths from other machines are never followed.
* Safety: the **raw reference string is never used to open a file**. Only
  the basename is resolved, always against the JSON's own folder
  (``folder / basename`` — a basename has no separator, so ``../``,
  absolute paths, drive letters and any path outside the config folder are
  structurally impossible). References whose basename is empty, ``.`` or
  ``..`` are dropped.

Result: :class:`ConfigDependencies` with ``obj_*`` and ``mp3_*`` fields.
Invalid JSON yields ``valid=False`` and no dependency claim.

Performance: JSON parsing is cached per file (keyed by path + mtime + size,
so an edit invalidates the entry). The existence checks — a cheap
``Path.is_file()`` per referenced name, at most a handful — are always
fresh, so adding/removing a mesh or sound is reflected immediately without
waiting for a re-parse. No directory scan ever happens here.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .models import ConfigItem

#: Strings starting with one of these schemes are remote (CDN) references:
#: Fleasion downloads them itself, no local file is involved.
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

#: A local mesh reference ends with ``.obj`` (trailing whitespace allowed).
_OBJ_END_RE = re.compile(r"\.obj\s*$", re.IGNORECASE)

#: A local sound reference ends with ``.mp3`` (case-insensitive: real files
#: are ``.MP3`` too).
_MP3_END_RE = re.compile(r"\.mp3\s*$", re.IGNORECASE)

_BACKSLASH = chr(92)  # "\\" — written via chr to keep the source portable


@dataclass(frozen=True)
class ConfigDependencies:
    """Dependencies of a configuration on local files.

    OBJ and MP3 are analysed independently and never mixed. ``valid`` is
    False when the JSON is unreadable or not an object — in that case no
    dependency claim is made.
    """

    valid: bool = False
    # -- OBJ ------------------------------------------------------------- #
    obj_required: bool = False
    obj_files: tuple[str, ...] = ()
    present_obj_files: tuple[str, ...] = ()
    missing_obj_files: tuple[str, ...] = ()
    # -- MP3 ------------------------------------------------------------- #
    mp3_required: bool = False
    mp3_files: tuple[str, ...] = ()
    present_mp3_files: tuple[str, ...] = ()
    missing_mp3_files: tuple[str, ...] = ()

    @property
    def incomplete(self) -> bool:
        """True when a referenced dependency is missing (needs attention)."""
        return bool(self.missing_obj_files) or bool(self.missing_mp3_files)


#: Backward-compatible alias (v1.1.0 name). New code should use
#: :class:`ConfigDependencies`; existing imports keep working.
ObjAnalysis = ConfigDependencies


def _referenced_name(value: str) -> str | None:
    """The file name referenced by a local path/name.

    Returns ``None`` for references whose basename is unusable (empty,
    ``.`` or ``..``) — those are dropped, never resolved.
    """
    name = value.split("/")[-1].split(_BACKSLASH)[-1].strip()
    if not name or name in (".", ".."):
        return None
    return name


def _parse_json(json_path: Path) -> tuple[bool, list[str], list[str]]:
    """Parse a JSON file and list its local ``.obj`` / ``.mp3`` references.

    Returns ``(valid, obj_names, mp3_names)`` — both lists are empty for
    invalid JSON. Only the **``replacement_rules`` array** is scanned
    (recursively, rules nest through ``children``): a string ending in
    ``.obj``/``.mp3`` that is not a URL is a local reference only when it
    lives inside an **active** rule (``enabled`` not ``False``). Strings
    anywhere else — sidecar metadata, descriptions, names, asset IDs — are
    never interpreted as a dependency: absence of a file is never the proof
    that it is required. The raw path is never used to open a file: only
    the basename, resolved against the JSON's own folder by the caller.
    """
    try:
        with open(json_path, "r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return False, [], []
    if not isinstance(data, dict):
        return False, [], []

    obj_names: list[str] = []
    mp3_names: list[str] = []
    seen_obj: set[str] = set()
    seen_mp3: set[str] = set()

    def scan_string(text: str) -> None:
        text = text.strip()
        if _URL_RE.match(text):
            return
        if _OBJ_END_RE.search(text):
            name = _referenced_name(text)
            if name is not None and name.casefold() not in seen_obj:
                seen_obj.add(name.casefold())
                obj_names.append(name)
        elif _MP3_END_RE.search(text):
            name = _referenced_name(text)
            if name is not None and name.casefold() not in seen_mp3:
                seen_mp3.add(name.casefold())
                mp3_names.append(name)

    def walk_rule(value: object, enabled: bool) -> None:
        """Recurse inside one replacement rule (or its nested children).

        ``enabled`` is the nearest enclosing rule's activation state: a
        child rule may carry its own ``enabled``, which is ANDed with the
        parent's. Disabled rules never contribute references.
        """
        if isinstance(value, dict):
            rule_enabled = enabled
            if isinstance(value.get("enabled"), bool):
                rule_enabled = enabled and value["enabled"]
            for child in value.values():
                walk_rule(child, rule_enabled)
        elif isinstance(value, list):
            for child in value:
                walk_rule(child, enabled)
        elif isinstance(value, str) and enabled:
            scan_string(value)

    rules = data.get("replacement_rules")
    if isinstance(rules, list):
        for rule in rules:
            walk_rule(rule, True)
    return True, obj_names, mp3_names


# ---------------------------------------------------------------------- #
# Cache: parse results keyed by (path, mtime_ns, size).
# ---------------------------------------------------------------------- #
_CACHE: dict[
    tuple[str, int, int], tuple[bool, tuple[str, ...], tuple[str, ...]]
] = {}
_CACHE_MAX = 512


def _cached_parse(
    json_path: Path,
) -> tuple[bool, tuple[str, ...], tuple[str, ...]]:
    """Parse a JSON file, cached until the file changes."""
    try:
        stat = json_path.stat()
        key = (str(json_path), stat.st_mtime_ns, stat.st_size)
    except OSError:
        key = (str(json_path), 0, 0)
    cached = _CACHE.get(key)
    if cached is not None:
        return cached
    valid, obj_names, mp3_names = _parse_json(json_path)
    result = (
        valid,
        tuple(sorted(set(obj_names), key=str.casefold)),
        tuple(sorted(set(mp3_names), key=str.casefold)),
    )
    if len(_CACHE) >= _CACHE_MAX:
        _CACHE.clear()
    _CACHE[key] = result
    return result


def clear_cache() -> None:
    """Drop all cached parses (used by tests and after bulk imports)."""
    _CACHE.clear()


def cache_size() -> int:
    """Number of currently cached JSON parses."""
    return len(_CACHE)


# ---------------------------------------------------------------------- #
# Public API
# ---------------------------------------------------------------------- #
def _analyze_json_file(json_path: Path) -> ConfigDependencies:
    """Analyse a single JSON file (existence checked fresh, never cached)."""
    valid, obj_names, mp3_names = _cached_parse(json_path)
    if not valid:
        return ConfigDependencies(valid=False)
    folder = json_path.parent

    present_obj = tuple(n for n in obj_names if (folder / n).is_file())
    missing_obj = tuple(n for n in obj_names if n not in present_obj)
    present_mp3 = tuple(n for n in mp3_names if (folder / n).is_file())
    missing_mp3 = tuple(n for n in mp3_names if n not in present_mp3)

    return ConfigDependencies(
        valid=True,
        obj_required=bool(obj_names),
        obj_files=obj_names,
        present_obj_files=present_obj,
        missing_obj_files=missing_obj,
        mp3_required=bool(mp3_names),
        mp3_files=mp3_names,
        present_mp3_files=present_mp3,
        missing_mp3_files=missing_mp3,
    )


def _merge(analyses: list[ConfigDependencies]) -> ConfigDependencies:
    """Merge per-file analyses (a folder configuration holds several JSONs)."""
    if not analyses:
        return ConfigDependencies(valid=False)
    if not all(a.valid for a in analyses):
        # An invalid JSON makes the configuration's dependencies unknown.
        return ConfigDependencies(valid=False)

    obj_files = sorted({n for a in analyses for n in a.obj_files}, key=str.casefold)
    present_obj = sorted(
        {n for a in analyses for n in a.present_obj_files}, key=str.casefold
    )
    missing_obj = sorted(
        {n for a in analyses for n in a.missing_obj_files}, key=str.casefold
    )
    mp3_files = sorted({n for a in analyses for n in a.mp3_files}, key=str.casefold)
    present_mp3 = sorted(
        {n for a in analyses for n in a.present_mp3_files}, key=str.casefold
    )
    missing_mp3 = sorted(
        {n for a in analyses for n in a.missing_mp3_files}, key=str.casefold
    )
    return ConfigDependencies(
        valid=True,
        obj_required=bool(obj_files),
        obj_files=tuple(obj_files),
        present_obj_files=tuple(present_obj),
        missing_obj_files=tuple(missing_obj),
        mp3_required=bool(mp3_files),
        mp3_files=tuple(mp3_files),
        present_mp3_files=tuple(present_mp3),
        missing_mp3_files=tuple(missing_mp3),
    )


def analyze_config(path: Path) -> ConfigDependencies:
    """Analyse a configuration's local OBJ/MP3 dependencies.

    ``path`` may be:

    * a ``.json`` file — that file is analysed;
    * a folder — every ``*.json`` inside is analysed and merged (folder
      configurations, e.g. a weapon folder acting as one configuration).

    Returns a :class:`ConfigDependencies`; never raises (unreadable or
    invalid JSON simply yields ``valid=False`` with no dependency claim).
    """
    path = Path(path)
    if path.is_dir():
        jsons = sorted(
            (p for p in path.iterdir() if p.suffix.lower() == ".json"),
            key=lambda p: p.name.lower(),
        )
        return _merge([_analyze_json_file(j) for j in jsons])
    if path.suffix.lower() == ".json":
        return _analyze_json_file(path)
    return ConfigDependencies(valid=False)


def analyze_item(item: ConfigItem) -> ConfigDependencies:
    """Analyse a library :class:`ConfigItem` (its JSON files)."""
    jsons = [p for p in item.json_files if p.suffix.lower() == ".json"]
    if not jsons:
        # A configuration with no JSON at all cannot require a dependency.
        return ConfigDependencies(valid=False)
    return _merge([_analyze_json_file(j) for j in jsons])
