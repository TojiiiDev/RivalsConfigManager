"""Tests for app/mod_import.py — mod import with zip-slip protection."""

from __future__ import annotations

import zipfile
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


from app.backup_manager import BackupManager
from app.mod_import import (
    MODE_KEEP_BOTH,
    MODE_REPLACE,
    Duplicate,
    ModFile,
    ModImportError,
    analyze_source,
    build_plan,
    cleanup_staging,
    install_mod,
)
from app.scanner import scan_library


def _make_zip(path: Path, entries: dict[str, str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return path


def _mod_zip(tmp_path: Path, name: str = "Gunblade_Black_Skin") -> Path:
    return _make_zip(
        tmp_path / f"{name}.zip",
        {
            f"{name}/config.json": '{"replacement_rules": []}',
            f"{name}/model.obj": "v 0 0 0",
            f"{name}/texture.png": "png",
        },
    )


# ---------------------------------------------------------------------- #
# Analysis
# ---------------------------------------------------------------------- #
def test_analyze_dir(tmp_path: Path) -> None:
    folder = tmp_path / "My Mod"
    folder.mkdir()
    (folder / "config.json").write_text("{}", encoding="utf-8")
    (folder / "model.obj").write_text("v", encoding="utf-8")

    analysis = analyze_source(folder)
    assert analysis.kind == "dir"
    assert analysis.name == "My Mod"
    assert {f.rel for f in analysis.files} == {"config.json", "model.obj"}
    assert analysis.obj_count == 1
    assert analysis.json_count == 1


def test_analyze_single_file(tmp_path: Path) -> None:
    obj = tmp_path / "Rival Skin.obj"
    obj.write_text("v 0 0 0", encoding="utf-8")

    analysis = analyze_source(obj)
    assert analysis.kind == "file"
    assert analysis.name == "Rival Skin"
    assert analysis.files == [ModFile("Rival Skin.obj", 7)]  # "v 0 0 0"
    assert analysis.staging is None


def test_analyze_zip_unwraps_single_folder(tmp_path: Path) -> None:
    zip_path = _mod_zip(tmp_path)
    staging_base = tmp_path / "staging"

    analysis = analyze_source(zip_path, staging_base=staging_base)
    assert analysis.kind == "zip"
    assert analysis.name == "Gunblade Black Skin"
    assert analysis.obj_count == 1
    assert {f.rel for f in analysis.files} == {"config.json", "model.obj", "texture.png"}

    cleanup_staging(analysis)
    assert not analysis.root.exists()


def test_zip_junk_is_ignored(tmp_path: Path) -> None:
    zip_path = _make_zip(
        tmp_path / "mod.zip",
        {
            "mod/config.json": "{}",
            "__MACOSX/._config.json": "x",
            "mod/.DS_Store": "y",
            "mod/Thumbs.db": "z",
        },
    )
    analysis = analyze_source(zip_path, staging_base=tmp_path / "staging")
    assert [f.rel for f in analysis.files] == ["mod/config.json"]  # junk filtered
    cleanup_staging(analysis)
    assert not analysis.staging.exists()


def test_zip_slip_entries_refused(tmp_path: Path) -> None:
    """``../``, absolute paths and drive letters must never extract outside
    the staging folder."""
    evil_entries = ["../../evil.json", "/tmp/evil.json", "C:/evil.json", r"..\evil.json"]
    for entry in evil_entries:
        zip_path = _make_zip(tmp_path / "evil.zip", {entry: "x"})
        with pytest.raises(ModImportError):
            analyze_source(zip_path, staging_base=tmp_path / "staging")
        # Nothing escaped the staging base.
        assert not (tmp_path / "evil.json").exists()
        assert not (tmp_path / "tmp" / "evil.json").exists()
        assert not (Path("C:/evil.json").exists())


def test_analyze_missing_source_raises(tmp_path: Path) -> None:
    with pytest.raises(ModImportError):
        analyze_source(tmp_path / "ghost.zip")


def test_empty_zip_raises(tmp_path: Path) -> None:
    zip_path = _make_zip(tmp_path / "empty.zip", {})
    with pytest.raises(ModImportError):
        analyze_source(zip_path, staging_base=tmp_path / "staging")


# ---------------------------------------------------------------------- #
# Planning + duplicates
# ---------------------------------------------------------------------- #
def test_build_plan_destination(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")
    analysis = analyze_source(src)
    library = tmp_path / "library"

    plan = build_plan("Energy Rifle Red", "secondary", "Energy Rifle", analysis, library)
    assert plan.destination == library / "Secondary" / "Energy Rifle" / "Energy Rifle Red"
    assert plan.duplicates == []


def test_build_plan_sanitizes_components(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")
    analysis = analyze_source(src)
    library = tmp_path / "library"

    plan = build_plan("../evil", "primary", "weapon/../x", analysis, library)
    assert plan.name == "evil"
    assert plan.weapon == "weapon..x"
    # The destination never contains a real ".." path component.
    assert all(part != ".." for part in plan.destination.relative_to(library).parts)


def test_duplicates_name_and_hash(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.json").write_text("same", encoding="utf-8")
    analysis = analyze_source(src)
    library = tmp_path / "library"
    dest = library / "Primary" / "My Mod"
    dest.mkdir(parents=True)
    (dest / "config.json").write_text("same", encoding="utf-8")
    (dest / "other.json").write_text("{}", encoding="utf-8")

    duplicates = build_plan("My Mod", "primary", None, analysis, library).duplicates
    kinds = {d.kind for d in duplicates}
    assert "name" in kinds
    assert "hash" in kinds  # config.json exists with identical content
    # The unrelated file is not reported.
    assert not any(d.existing.name == "other.json" for d in duplicates)


def test_duplicates_different_content(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.json").write_text("new", encoding="utf-8")
    analysis = analyze_source(src)
    library = tmp_path / "library"
    dest = library / "Primary" / "My Mod"
    dest.mkdir(parents=True)
    (dest / "config.json").write_text("old", encoding="utf-8")

    duplicates = build_plan("My Mod", "primary", None, analysis, library).duplicates
    assert any(d.kind == "file" and "différent" in d.details for d in duplicates)


# ---------------------------------------------------------------------- #
# Installation
# ---------------------------------------------------------------------- #
def test_install_copies_files(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.json").write_text('{"a": 1}', encoding="utf-8")
    (src / "model.obj").write_text("v 0 0 0", encoding="utf-8")
    analysis = analyze_source(src)
    library = tmp_path / "library"

    plan = build_plan("My Mod", "primary", "My Weapon", analysis, library)
    destination = install_mod(plan)
    assert destination == library / "Primary" / "My Weapon" / "My Mod"
    assert (destination / "config.json").read_text(encoding="utf-8") == '{"a": 1}'
    assert (destination / "model.obj").read_text(encoding="utf-8") == "v 0 0 0"


def test_install_keep_both_uses_suffix(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")
    analysis = analyze_source(src)
    library = tmp_path / "library"
    library.mkdir()
    existing = library / "Primary" / "My Mod"
    existing.mkdir(parents=True)
    (existing / "config.json").write_text("old", encoding="utf-8")

    plan = build_plan("My Mod", "primary", None, analysis, library, mode=MODE_KEEP_BOTH)
    destination = install_mod(plan)
    assert destination.name == "My Mod (2)"
    # The existing mod is untouched.
    assert (existing / "config.json").read_text(encoding="utf-8") == "old"


def test_install_replace_backs_up_and_overwrites(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.json").write_text("new", encoding="utf-8")
    analysis = analyze_source(src)
    library = tmp_path / "library"
    existing = library / "Primary" / "My Mod"
    existing.mkdir(parents=True)
    (existing / "config.json").write_text("old", encoding="utf-8")
    backups = BackupManager(tmp_path / "backups")

    plan = build_plan("My Mod", "primary", None, analysis, library, mode=MODE_REPLACE)
    destination = install_mod(plan, backups)
    assert (destination / "config.json").read_text(encoding="utf-8") == "new"
    infos = backups.list_backups()
    assert infos, "aucune sauvegarde avant remplacement"
    backed = infos[0].folder / "config.json"
    assert backed.exists() and backed.read_text(encoding="utf-8") == "old"


def test_install_replace_without_backup_refused(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.json").write_text("new", encoding="utf-8")
    analysis = analyze_source(src)
    library = tmp_path / "library"
    existing = library / "Primary" / "My Mod"
    existing.mkdir(parents=True)
    (existing / "config.json").write_text("old", encoding="utf-8")

    plan = build_plan("My Mod", "primary", None, analysis, library, mode=MODE_REPLACE)
    with pytest.raises(ModImportError):
        install_mod(plan, None)  # no backup manager -> refusal
    assert (existing / "config.json").read_text(encoding="utf-8") == "old"


def test_install_refuses_unsafe_paths(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")
    (tmp_path / "evil.json").write_text("x", encoding="utf-8")
    analysis = analyze_source(src)
    library = tmp_path / "library"

    # A crafted plan with an escaping relative path is refused at install.
    plan = build_plan("My Mod", "primary", None, analysis, library)
    plan.files.append(ModFile("../evil.json", 0))
    with pytest.raises(ModImportError):
        install_mod(plan)
    assert not (library / "evil.json").exists()


def test_install_missing_mod_file_raises(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")
    analysis = analyze_source(src)
    library = tmp_path / "library"

    plan = build_plan("My Mod", "primary", None, analysis, library)
    plan.files.append(ModFile("ghost.obj", 0))
    with pytest.raises(ModImportError):
        install_mod(plan)


def test_imported_mod_appears_in_library_scan(tmp_path: Path) -> None:
    """End to end: a ZIP becomes a browsable configuration in the library."""
    library = tmp_path / "library"
    library.mkdir()
    zip_path = _mod_zip(tmp_path)

    analysis = analyze_source(zip_path, staging_base=tmp_path / "staging")
    plan = build_plan(analysis.name, "primary", None, analysis, library)
    install_mod(plan)
    cleanup_staging(analysis)

    node = scan_library(library).node
    primary = next(s for s in node.subdirs if s.name == "Primary")
    mod = next(c for c in primary.configs if c.name == "Gunblade Black Skin")
    assert mod.is_folder
    assert (mod.path / "model.obj").exists()


def test_import_texture_pack_into_custom_category(tmp_path: Path) -> None:
    """A non-weapon pack (textures) installs into the chosen library
    category (not forced into a weapon category) and shows up there."""
    library = tmp_path / "library"
    (library / "Textures").mkdir(parents=True)
    src = tmp_path / "Neon Texture Pack"
    src.mkdir()
    (src / "config.json").write_text('{"replacement_rules": []}', encoding="utf-8")
    (src / "albedo.png").write_bytes(b"png")

    analysis = analyze_source(src)
    plan = build_plan(analysis.name, "Textures", None, analysis, library)
    assert plan.destination == library / "Textures" / "Neon Texture Pack"
    destination = install_mod(plan)
    assert destination == library / "Textures" / "Neon Texture Pack"

    node = scan_library(library).node
    textures = next(s for s in node.subdirs if s.name == "Textures")
    mod = next(c for c in textures.configs if c.name == "Neon Texture Pack")
    assert mod.is_folder
    assert (mod.path / "albedo.png").exists()
    # The pre-existing category folder is untouched (same path, same name).
    assert textures.path == library / "Textures"


def test_import_into_empty_existing_category(tmp_path: Path) -> None:
    """An empty existing category is a valid destination."""
    library = tmp_path / "library"
    (library / "Skins").mkdir(parents=True)  # vide
    src = tmp_path / "Skin Pack"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")
    (src / "preview.png").write_bytes(b"png")

    analysis = analyze_source(src)
    plan = build_plan("Skin Pack", "Skins", None, analysis, library)
    destination = install_mod(plan)
    assert destination == library / "Skins" / "Skin Pack"

    node = scan_library(library).node
    skins = next(s for s in node.subdirs if s.name == "Skins")
    assert any(c.name == "Skin Pack" for c in skins.configs)


def test_build_plan_refuses_out_of_library_category(tmp_path: Path) -> None:
    """A crafted category must never escape the library root."""
    library = tmp_path / "library"
    library.mkdir()
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")
    analysis = analyze_source(src)

    for evil in ("../escape", "..\\escape", "/abs", "C:/evil"):
        with pytest.raises(ModImportError):
            build_plan("Evil", evil, None, analysis, library)
    assert not (tmp_path / "escape").exists()
    assert not (tmp_path / "evil").exists()


def test_build_plan_accepts_custom_category_inside_library(tmp_path: Path) -> None:
    """A normal library folder name (even with spaces) stays a valid,
    in-library destination."""
    library = tmp_path / "library"
    (library / "Texture and skyboxes").mkdir(parents=True)
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")
    analysis = analyze_source(src)

    plan = build_plan("Sky Pack", "Texture and skyboxes", None, analysis, library)
    assert plan.destination == library / "Texture and skyboxes" / "Sky Pack"


# ---------------------------------------------------------------------- #
# Regression: destination must never duplicate the weapon folder name
# ---------------------------------------------------------------------- #
def test_destination_no_weapon_duplication(tmp_path: Path) -> None:
    """Choosing Primary -> Assault Rifle must produce
    Primary/Assault Rifle/<config>, NOT Primary/Assault Rifle/Assault Rifle/<config>.
    """
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")
    analysis = analyze_source(src)
    library = tmp_path / "library"

    plan = build_plan("Assault Rifle", "primary", "Assault Rifle", analysis, library)
    # Must NOT be: library/Primary/Assault Rifle/Assault Rifle
    assert plan.destination == library / "Primary" / "Assault Rifle"


def test_destination_mod_name_differs_from_weapon(tmp_path: Path) -> None:
    """A mod name that differs from the weapon creates its own folder."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")
    analysis = analyze_source(src)
    library = tmp_path / "library"

    plan = build_plan("Golden Skin", "primary", "Assault Rifle", analysis, library)
    assert plan.destination == library / "Primary" / "Assault Rifle" / "Golden Skin"


def test_destination_weapon_case_insensitive_match(tmp_path: Path) -> None:
    """Case differences between mod name and weapon are ignored."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")
    analysis = analyze_source(src)
    library = tmp_path / "library"

    plan = build_plan("assault rifle", "primary", "Assault Rifle", analysis, library)
    assert plan.destination == library / "Primary" / "Assault Rifle"


def test_destination_no_weapon_no_duplication(tmp_path: Path) -> None:
    """Without a weapon, the mod name is used normally."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")
    analysis = analyze_source(src)
    library = tmp_path / "library"

    plan = build_plan("My Skin", "primary", None, analysis, library)
    assert plan.destination == library / "Primary" / "My Skin"


def test_destination_multiple_items_different_weapons(tmp_path: Path) -> None:
    """Multiple mods for different weapons: no duplication."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")
    analysis = analyze_source(src)
    library = tmp_path / "library"

    plan1 = build_plan("Assault Rifle", "primary", "Assault Rifle", analysis, library)
    plan2 = build_plan("Gunblade", "melee", "Gunblade", analysis, library)
    plan3 = build_plan("Silver Skin", "primary", "Assault Rifle", analysis, library)

    assert plan1.destination == library / "Primary" / "Assault Rifle"
    assert plan2.destination == library / "Melee" / "Gunblade"
    assert plan3.destination == library / "Primary" / "Assault Rifle" / "Silver Skin"
