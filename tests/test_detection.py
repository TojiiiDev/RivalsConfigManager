"""Tests for app/detection.py — automatic weapon/category detection.

The detection must be *conservative*: solid matches are proposed with
high confidence, ambiguous ones are flagged, and a mod is never assigned
a category/weapon it does not clearly belong to.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _french_messages():
    """Messages applicatifs en français — le défaut 1.3.13 est l'anglais,
    ces tests vérifient les textes français (restaurés après)."""
    from app.i18n import current_language, set_language

    previous = current_language()
    set_language("fr")
    yield
    set_language(previous)


from app.detection import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    detect,
    weapons_for_category,
)


def _library(root: Path) -> Path:
    """A small library with category folders and weapon subfolders."""
    for category, weapons in {
        "Primary": ["Assault Rifle", "Shotgun"],
        "Secondary": ["Energy Rifle", "Hand gun"],
        "Melee": ["Gunblade", "Battle Axe"],
        "Utility": ["Grappling Hook"],
    }.items():
        for weapon in weapons:
            (root / category / weapon).mkdir(parents=True)
    return root


# ---------------------------------------------------------------------- #
# Known weapons registry
# ---------------------------------------------------------------------- #
def test_gunblade_skin_detected_melee() -> None:
    det = detect("Gunblade Black Skin")
    assert det.category == "melee"
    assert det.weapon == "Gunblade"
    assert det.confidence == CONFIDENCE_HIGH
    assert det.source == "règles connues"
    assert det.label == "Mêlée → Gunblade"


def test_underscore_name_detected() -> None:
    """The zip name as it comes from the file system (underscores)."""
    det = detect("Gunblade_Black_Skin")
    assert det.category == "melee"
    assert det.weapon == "Gunblade"


def test_energy_rifle_detected_secondary() -> None:
    det = detect("Energy Rifle Red")
    assert det.category == "secondary"
    assert det.weapon == "Energy Rifle"
    assert det.confidence == CONFIDENCE_HIGH


def test_melee_sword_detected_melee() -> None:
    """« Melee Sword » contains the weapon « Sword » (whole word)."""
    det = detect("Melee Sword")
    assert det.category == "melee"
    assert det.weapon == "Sword"
    assert det.confidence == CONFIDENCE_MEDIUM


def test_version_tag_stripped() -> None:
    det = detect("Assault Rifle V2")
    assert det.category == "primary"
    assert det.weapon == "Assault Rifle"
    assert det.confidence == CONFIDENCE_HIGH


def test_number_suffix_stripped() -> None:
    det = detect("Gunblade (1)")
    assert det.category == "melee"
    assert det.weapon == "Gunblade"


def test_pistol_pack_detected_secondary() -> None:
    det = detect("Pistol Skins Pack")
    assert det.category == "secondary"
    assert det.weapon == "Pistol"
    assert det.confidence == CONFIDENCE_HIGH


def test_single_weapon_word() -> None:
    det = detect("Shotgun")
    assert det.category == "primary"
    assert det.weapon == "Shotgun"


# ---------------------------------------------------------------------- #
# Low confidence — no false positives
# ---------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name",
    [
        "Energy",       # part of « Energy Rifle », but not the weapon itself
        "Assault",      # part of « Assault Rifle »
        "Cool Random Pack",
        "Mystery Item",
    ],
)
def test_ambiguous_names_are_low_confidence(name: str) -> None:
    det = detect(name)
    assert det.confidence == CONFIDENCE_LOW
    assert det.category is None
    assert det.weapon is None
    assert not det.found


def test_empty_name_low_confidence() -> None:
    det = detect("")
    assert det.confidence == CONFIDENCE_LOW
    assert not det.found


def test_stripped_to_nothing_falls_back_to_raw() -> None:
    det = detect("Mod")
    assert det.confidence == CONFIDENCE_LOW


# ---------------------------------------------------------------------- #
# Library structure is the strongest signal
# ---------------------------------------------------------------------- #
def test_library_structure_detects_weapon(tmp_path: Path) -> None:
    det = detect("Assault Rifle Gold", _library(tmp_path))
    assert det.category == "primary"
    assert det.weapon == "Assault Rifle"
    assert det.confidence == CONFIDENCE_HIGH
    assert det.source == "votre bibliothèque"


def test_library_detects_gunblade(tmp_path: Path) -> None:
    det = detect("Gunblade Black Skin", _library(tmp_path))
    assert det.category == "melee"
    assert det.weapon == "Gunblade"
    assert det.confidence == CONFIDENCE_HIGH


def test_library_preserves_folder_casing(tmp_path: Path) -> None:
    det = detect("hand gun skin", _library(tmp_path))
    assert det.category == "secondary"
    assert det.weapon == "Hand gun"  # real folder name, not the registry casing


def test_library_longest_match_wins(tmp_path: Path) -> None:
    """« Battle Axe Nordic » matches « Battle Axe », not the shorter « Axe »."""
    det = detect("Battle Axe Nordic", _library(tmp_path))
    assert det.category == "melee"
    assert det.weapon == "Battle Axe"


def test_library_does_not_invent_weapons(tmp_path: Path) -> None:
    """A mod name must contain the weapon folder name: « Skins Pack » is
    not a weapon just because it sits under a category folder."""
    det = detect("Skins Pack Mod", _library(tmp_path))
    assert det.confidence == CONFIDENCE_LOW


def test_library_missing_falls_back_to_registry(tmp_path: Path) -> None:
    det = detect("Gunblade Black Skin", tmp_path / "ghost")
    assert det.category == "melee"
    assert det.weapon == "Gunblade"
    assert det.source == "règles connues"


# ---------------------------------------------------------------------- #
# Category-only packs
# ---------------------------------------------------------------------- #
def test_category_pack_gets_category_only(tmp_path: Path) -> None:
    det = detect("Melee Skins Pack", _library(tmp_path))
    assert det.category == "melee"
    assert det.weapon is None
    assert det.confidence == CONFIDENCE_MEDIUM
    assert det.label == "Mêlée"


def test_french_category_pack(tmp_path: Path) -> None:
    det = detect("Pack Secondaire", _library(tmp_path))
    assert det.category == "secondary"
    assert det.weapon is None


# ---------------------------------------------------------------------- #
# Detection without a library folder (registry path only)
# ---------------------------------------------------------------------- #
def test_detect_without_library() -> None:
    det = detect("Energy Rifle Red")
    assert det.category == "secondary"
    assert det.weapon == "Energy Rifle"
    assert det.confidence == CONFIDENCE_HIGH


# ---------------------------------------------------------------------- #
# Weapon picker list per category
# ---------------------------------------------------------------------- #
def test_weapons_for_category_library_then_registry(tmp_path: Path) -> None:
    lib = _library(tmp_path)
    weapons = weapons_for_category(lib, "melee")
    # Library folders come first, registry weapons complete the list.
    assert "Gunblade" in weapons
    assert "Battle Axe" in weapons
    assert "Katana" in weapons  # registry only
    # De-duplicated (Gunblade/Battle Axe exist both in the library and
    # in the registry).
    assert len(weapons) == len(set(weapons))


def test_weapons_for_category_keeps_weapons_out_of_other_categories(tmp_path: Path) -> None:
    lib = _library(tmp_path)
    weapons = weapons_for_category(lib, "primary")
    assert "Assault Rifle" in weapons
    assert "Shotgun" in weapons
    assert "Gunblade" not in weapons
    assert "Energy Rifle" not in weapons


def test_weapons_for_category_missing_library_uses_registry_only() -> None:
    weapons = weapons_for_category(None, "secondary")
    assert "Energy Rifle" in weapons
    assert "Pistol" in weapons
    assert "Shotgun" not in weapons


def test_weapons_for_category_sorted() -> None:
    weapons = weapons_for_category(None, "primary")
    assert weapons == sorted(weapons, key=str.casefold)


# ---------------------------------------------------------------------- #
# Source dependencies (v1.3.0) : OBJ / MP3 détectés à l'import
# ---------------------------------------------------------------------- #
def _mod_analysis(root: Path, files: list[tuple[str, str]]) -> object:
    """A minimal ModAnalysis-like object (root + files with rel paths)."""
    from types import SimpleNamespace

    items = [SimpleNamespace(rel=rel, path=root / rel) for rel, _ in files]
    for rel, content in files:
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
    return SimpleNamespace(root=str(root), files=items)


def test_source_deps_detected_by_extension(tmp_path: Path) -> None:
    from app.detection import detect_source_dependencies

    analysis = _mod_analysis(
        tmp_path,
        [("model.obj", "mesh"), ("sound.mp3", b"ID3".decode())],
    )
    deps = detect_source_dependencies(analysis)
    assert deps.obj and deps.mp3
    assert deps.any


def test_source_deps_detected_in_json(tmp_path: Path) -> None:
    import json as _json

    from app.detection import detect_source_dependencies

    analysis = _mod_analysis(
        tmp_path,
        [("skin.json", _json.dumps({"replacement_rules": [{"cdn_url": "body.obj"}]}))],
    )
    deps = detect_source_dependencies(analysis)
    assert deps.obj
    assert not deps.mp3


def test_source_deps_ignores_remote_urls(tmp_path: Path) -> None:
    import json as _json

    from app.detection import detect_source_dependencies

    analysis = _mod_analysis(
        tmp_path,
        [("skin.json", _json.dumps({"replacement_rules": [{"cdn_url": "https://x/body.obj"}]}))],
    )
    deps = detect_source_dependencies(analysis)
    assert not deps.obj  # URL distante : pas une dépendance locale
    assert not deps.any


def test_source_deps_none_when_no_mesh_no_sound(tmp_path: Path) -> None:
    import json as _json

    from app.detection import detect_source_dependencies

    analysis = _mod_analysis(
        tmp_path,
        [("skin.json", _json.dumps({"replacement_rules": []}))],
    )
    deps = detect_source_dependencies(analysis)
    assert not deps.obj
    assert not deps.mp3
    assert not deps.any
