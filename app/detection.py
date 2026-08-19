"""Automatic weapon + category detection when importing a mod.

The import dialog lets the user pick the category and weapon manually
(step 7). This module (step 8) tries to *pre-fill* those fields so that
importing ``Gunblade_Black_Skin.zip`` lands directly in
``Melee/Gunblade`` without any manual step — but only when the evidence
is solid.

Detection is deliberately conservative:

1. the **user's own library structure** is the strongest signal — if the
   library already has a ``Melee/Gunblade`` folder, a mod named
   ``Gunblade Black Skin`` belongs there (:data:`CONFIDENCE_HIGH`);
2. otherwise the built-in :data:`KNOWN_WEAPONS` registry proposes a
   category (exact/prefix match → :data:`CONFIDENCE_HIGH`, mere
   containment → :data:`CONFIDENCE_MEDIUM`);
3. a mod whose name *is* a category (« Melee Skins Pack ») gets the
   category only (:data:`CONFIDENCE_MEDIUM`);
4. when nothing matches, the detection says so (:data:`CONFIDENCE_LOW`)
   and the user chooses manually — a mod is never silently placed in a
   guessed folder.

Skin-ish suffixes (``_Skin``, colors, version tags, numbers in
parentheses, ...) are stripped before matching, so ``Gunblade_Black_Skin``
is matched against ``Gunblade``.

Nothing in this module writes to disk: detection only *proposes* values
that remain editable in the preview dialog, and the final decision always
stays with the user.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .categories import CATEGORY_KEYS, category_rank, display_label
from .i18n import t

#: Confidence levels, from strongest to weakest.
CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

#: Known weapons per canonical category. Keys are lower-case names with
#: spaces instead of separators. Extend this list freely; it is only a
#: fallback — the user's library structure takes precedence.
KNOWN_WEAPONS: dict[str, str] = {
    # Primaire
    "assault rifle": "primary",
    "ar": "primary",
    "burst rifle": "primary",
    "burst": "primary",
    "shotgun": "primary",
    "combat shotgun": "primary",
    "sniper": "primary",
    "sniper rifle": "primary",
    "lmg": "primary",
    "light machine gun": "primary",
    "battle rifle": "primary",
    "marksman": "primary",
    "lever action": "primary",
    # Secondaire
    "pistol": "secondary",
    "revolver": "secondary",
    "energy rifle": "secondary",
    "pdw": "secondary",
    "smg": "secondary",
    "submachine gun": "secondary",
    "machine pistol": "secondary",
    "handgun": "secondary",
    "hand gun": "secondary",
    "desert eagle": "secondary",
    # Mêlée
    "gunblade": "melee",
    "katana": "melee",
    "sword": "melee",
    "dagger": "melee",
    "knife": "melee",
    "baseball bat": "melee",
    "bat": "melee",
    "crowbar": "melee",
    "sledgehammer": "melee",
    "hammer": "melee",
    "axe": "melee",
    "battle axe": "melee",
    "tonfa": "melee",
    "spear": "melee",
    "machete": "melee",
    # Utilitaire
    "grappling hook": "utility",
    "grapple": "utility",
    "flashlight": "utility",
    "flash light": "utility",
    "medkit": "utility",
    "med kit": "utility",
    "shield": "utility",
}

#: Trailing words that are skin/variant noise, stripped before matching.
_SKIN_WORDS = frozenset(
    {
        "skin", "skins", "black", "white", "red", "blue", "green",
        "purple", "pink", "orange", "yellow", "gold", "silver", "grey",
        "gray", "dark", "light", "neon", "glow", "glowing", "chrome",
        "carbon", "digital", "classic", "retro", "deluxe", "ultimate",
        "hd", "final", "remaster", "rework", "pack", "bundle",
        "collection", "set", "addon", "mod",
    }
)

#: Version tags such as ``v1.0``, ``2`` or ``(3)`` (parentheses removed
#: before matching).
_VERSION_RE = re.compile(r"^v?\d+(\.\d+)*$")

#: Leading noise words removed before matching (« Pack Secondaire »).
_LEADING_WORDS = frozenset({"pack", "bundle", "collection", "set", "mod", "skin", "skins"})

#: Trailing version/noise words removed from a mod **name** (not from
#: detection): « Pixel_Catana_Final_v2 » → « Pixel Catana ». Colors and
#: « skin » words are kept — they belong to the mod name.
_NAME_NOISE = frozenset(
    {"final", "updated", "update", "new", "latest", "remaster", "rework", "v1", "v2", "v3", "hd"}
)


@dataclass(frozen=True)
class Detection:
    """The result of an automatic detection: what to pre-fill and how
    confident the app is about it."""

    weapon: str | None = None
    category: str | None = None
    confidence: str = CONFIDENCE_LOW
    source: str = ""

    @property
    def found(self) -> bool:
        """True when at least a category was identified."""
        return self.category is not None

    @property
    def label(self) -> str:
        """Human-readable summary (« Mêlée → Gunblade »)."""
        if self.category is None:
            return t("detection.inconclusive")
        cat = display_label(self.category)
        if self.weapon:
            return t("detection.category_weapon", category=cat, weapon=self.weapon)
        return cat


def detect(mod_name: str, library_root: Path | None = None) -> Detection:
    """Propose a weapon + category for a mod name.

    ``library_root`` is the user's library folder; its structure is the
    strongest evidence. Returns a :class:`Detection` that is always safe
    to ignore (the caller keeps full control).
    """
    return detect_source_name(mod_name, library_root)


def detect_source_name(mod_name: str, library_root: Path | None = None) -> Detection:
    """Name-based detection (see :func:`detect`)."""
    raw = _normalize(mod_name)
    stem = _strip_suffixes(raw) or raw
    if not stem:
        return Detection(confidence=CONFIDENCE_LOW, source=t("detection.source_none"))

    # 1. The user's own library structure is the strongest signal.
    if library_root is not None:
        weapon, category = _match_pairs(stem, _library_weapon_pairs(library_root))
        if category is not None:
            return Detection(
                weapon=weapon,
                category=category,
                confidence=CONFIDENCE_HIGH,
                source=t("detection.source_library"),
            )

    # 2. Known weapons registry.
    weapon, category, confidence = _match_registry(stem)
    if category is not None:
        return Detection(
            weapon=weapon,
            category=category,
            confidence=confidence,
            source=t("detection.source_known"),
        )

    # 3. The name itself is a category (« Melee Skins Pack »).
    rank = category_rank(stem)
    if rank is not None:
        return Detection(
            category=CATEGORY_KEYS[rank],
            confidence=CONFIDENCE_MEDIUM,
            source=t("detection.source_category"),
        )

    return Detection(confidence=CONFIDENCE_LOW, source=t("detection.source_none"))


# ---------------------------------------------------------------------- #
# Source content analysis (1.3.0)
# ---------------------------------------------------------------------- #
@dataclass(frozen=True)
class SourceDependencies:
    """Dependencies detected by scanning a mod **source** (staged files).

    Unlike the library analysis, this only tells the user what the mod
    *contains* (meshes / sounds) to pre-fill the import — the final
    decision always stays with the user.
    """

    obj: bool = False
    mp3: bool = False

    @property
    def any(self) -> bool:
        return self.obj or self.mp3

    @property
    def label(self) -> str:
        """Human-readable summary (translated), e.g. « ✓ OBJ, ✓ MP3 »."""
        parts = []
        if self.obj:
            parts.append(t("detection.obj"))
        if self.mp3:
            parts.append(t("detection.mp3"))
        return t("detection.deps", deps=", ".join(parts))


def detect_source_dependencies(analysis) -> SourceDependencies:
    """Detect whether a mod source contains meshes (``.obj``) and/or
    sounds (``.mp3``) — by extension first, then by scanning the JSON
    strings (reusing the exact library detection convention, including the
    « URLs are remote » rule).

    ``analysis`` is a :class:`app.mod_import.ModAnalysis` whose ``root``
    points at the staged/source files. Read-only, never writes.
    """
    obj = False
    mp3 = False
    for f in analysis.files:
        lower = f.rel.lower()
        if lower.endswith(".obj"):
            obj = True
        elif lower.endswith(".mp3"):
            mp3 = True
    # JSON content: reuse the library's convention (bare names = local
    # deps, full URLs = remote and ignored).
    try:
        from .config_analysis import _parse_json

        root = Path(analysis.root)
        for rel in (f.rel for f in analysis.files if f.rel.lower().endswith(".json")):
            valid, obj_names, mp3_names = _parse_json(root / rel)
            if not valid:
                continue
            if obj_names:
                obj = True
            if mp3_names:
                mp3 = True
    except Exception:  # pragma: no cover - defensive: detection never crashes
        pass
    return SourceDependencies(obj=obj, mp3=mp3)


def weapons_for_category(library_root: Path | None, category: str) -> list[str]:
    """Weapon names proposed for a category, for the import picker.

    The user's own library folders come first (they reflect the real
    organisation), then the built-in registry, de-duplicated and sorted
    alphabetically.
    """
    names: list[str] = []
    seen: set[str] = set()
    if library_root is not None:
        for weapon_name, cat in _library_weapon_pairs(library_root):
            if cat == category:
                key = _normalize(weapon_name)
                if key not in seen:
                    seen.add(key)
                    names.append(weapon_name)
    for weapon_key, cat in KNOWN_WEAPONS.items():
        if cat == category and weapon_key not in seen:
            seen.add(weapon_key)
            names.append(_display_weapon(weapon_key))
    return sorted(names, key=str.casefold)


# ---------------------------------------------------------------------- #
# Library structure
# ---------------------------------------------------------------------- #
def _library_weapon_entries(
    library_root: Path, max_depth: int = 5
) -> list[tuple[str, Path, str]]:
    """``(weapon folder name, folder path, category key)`` triples found in
    the library.

    Whenever a folder is recognised as a weapon category (Primary,
    Secondary, Melee, Utility — EN or FR), its **direct** subfolders are
    considered weapons. Grandchildren are not recorded: a folder named
    « skins pack » inside a weapon must never be proposed as a weapon.
    """
    entries: list[tuple[str, Path, str]] = []
    root = Path(library_root)
    if not root.is_dir():
        return entries

    def walk(folder: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            children = sorted(folder.iterdir())
        except OSError:
            return
        for entry in children:
            if not entry.is_dir():
                continue
            rank = category_rank(entry.name)
            if rank is None:
                walk(entry, depth + 1)
                continue
            key = CATEGORY_KEYS[rank]
            for sub in sorted(entry.iterdir()):
                if sub.is_dir():
                    entries.append((sub.name, sub, key))
            walk(entry, depth + 1)

    walk(root, 0)
    return entries


def _library_weapon_pairs(library_root: Path, max_depth: int = 5) -> list[tuple[str, str]]:
    """``(weapon folder name, category key)`` pairs found in the library."""
    return [(name, cat) for name, _path, cat in _library_weapon_entries(library_root, max_depth)]


def weapon_folders(
    library_root: Path | None, category: str
) -> list[tuple[str, Path]]:
    """``(weapon name, folder path)`` pairs for a category, from the real
    library folders — used by the import popup to show each weapon's image."""
    if library_root is None:
        return []
    return [
        (name, path)
        for name, path, cat in _library_weapon_entries(library_root)
        if cat == category
    ]


def _match_pairs(stem: str, pairs: list[tuple[str, str]]) -> tuple[str | None, str | None]:
    """Longest weapon folder name contained in ``stem`` (whole words)."""
    best: tuple[int, str, str] | None = None
    for weapon_name, category in pairs:
        w = _normalize(weapon_name)
        if len(w) < 3 or not _contains_sequence(stem, w):
            continue
        if best is None or len(w) > best[0]:
            best = (len(w), weapon_name, category)
    if best is None:
        return None, None
    return best[1], best[2]


# ---------------------------------------------------------------------- #
# Known weapons registry
# ---------------------------------------------------------------------- #
def _match_registry(stem: str) -> tuple[str | None, str | None, str]:
    """``(weapon, category, confidence)`` from :data:`KNOWN_WEAPONS`.

    A weapon found at the **start** of the name (``Gunblade Black Skin``)
    is :data:`CONFIDENCE_HIGH`; a mere whole-word containment
    (``Melee Sword`` contains « sword ») is :data:`CONFIDENCE_MEDIUM`.
    """
    best: tuple[int, str, str, str] | None = None  # (len, weapon, category, confidence)
    for weapon_key, category in KNOWN_WEAPONS.items():
        if not _contains_sequence(stem, weapon_key):
            continue
        if stem == weapon_key or stem.startswith(weapon_key + " "):
            confidence = CONFIDENCE_HIGH
        else:
            confidence = CONFIDENCE_MEDIUM
        if best is None or len(weapon_key) > best[0]:
            best = (len(weapon_key), weapon_key, category, confidence)
    if best is None:
        return None, None, CONFIDENCE_LOW
    _, weapon, category, confidence = best
    return _display_weapon(weapon), category, confidence


def _display_weapon(key: str) -> str:
    return " ".join(part.capitalize() for part in key.split())


# ---------------------------------------------------------------------- #
# Name analysis
# ---------------------------------------------------------------------- #
def suggest_name(raw_name: str) -> str:
    """A clean, user-friendly mod name for the import popup.

    Separators become spaces and trailing version/noise words are removed
    (« Pixel_Catana_Final_v2 » → « Pixel Katana »). The source file is
    never renamed: this only pre-fills the name field, which the user can
    freely edit before installing.
    """
    words = " ".join(raw_name.replace("_", " ").replace("-", " ").split()).split()
    while words:
        word = words[-1].strip("()")
        if word.casefold() in _NAME_NOISE or _VERSION_RE.match(word):
            words.pop()
        else:
            break
    return " ".join(words) or raw_name.strip()


def _normalize(text: str) -> str:
    """Lower-case, collapse whitespace, treat ``_``/``-`` as spaces."""
    return " ".join(text.replace("_", " ").replace("-", " ").split()).casefold()


def _strip_suffixes(name: str) -> str:
    """Remove trailing skin-ish words (« Gunblade Black Skin » → « Gunblade »)
    and leading pack words (« Pack Secondaire » → « Secondaire »)."""
    words = name.split()
    while words:
        word = words[-1].strip("()")
        if word.casefold() in _SKIN_WORDS or _VERSION_RE.match(word):
            words.pop()
        else:
            break
    while words:
        word = words[0].strip("()")
        if word.casefold() in _LEADING_WORDS:
            words.pop(0)
        else:
            break
    return " ".join(words)


def _contains_sequence(text: str, seq: str) -> bool:
    """True when the normalized ``seq`` appears in ``text`` as whole words."""
    if " " not in seq:
        return seq in text.split()
    return seq in text
