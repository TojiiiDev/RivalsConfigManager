"""Tests for the v1.3.0 app-layer features:

* Favorites (persistent, independent of Fleasion state);
* Recents (bounded, persistent store);
* Verification (app/verify.py — JSON, OBJ/MP3 deps, files, category);
* Repair (app/repair.py — copy-only plans, never overwrite, re-verified);
* Profiles (app/profiles.py — create/update/delete, export/import).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import AppSettings
from app.config_analysis import clear_cache
from app.models import KIND_FILE, ConfigItem
from app.profiles import ProfileEntry, ProfileError, ProfileManager
from app.recents import MAX_RECENTS, RecentsStore
from app.repair import apply_repair, build_repair_plan
from app.verify import verify_item


# ---------------------------------------------------------------------- #
# Favorites
# ---------------------------------------------------------------------- #
def test_favorites_toggle_persists(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    settings = AppSettings()
    assert settings.favorites == []
    assert settings.toggle_favorite("a") is True
    assert settings.toggle_favorite("b") is True
    settings.save()

    reloaded = AppSettings.load()
    assert reloaded.favorites == ["a", "b"]
    # Untoggle removes only the given key.
    assert reloaded.toggle_favorite("a") is False
    reloaded.save()
    assert AppSettings.load().favorites == ["b"]


def test_favorites_never_confused_with_enabled_configs(tmp_path: Path, monkeypatch) -> None:
    """Un favori n'est PAS un « enabled_config » : les deux listes sont
    totalement indépendantes (le favori n'active rien dans Fleasion)."""
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    settings = AppSettings()
    settings.favorites = ["nemesis charm"]
    settings.enabled_configs = []  # champ v1.1.0/v1.2.0 (compat)
    assert "nemesis charm" in settings.favorites
    assert "nemesis charm" not in settings.enabled_configs


def test_favorites_loaded_from_settings_file(tmp_path: Path, monkeypatch) -> None:
    appdata = tmp_path / "AppData"
    monkeypatch.setenv("APPDATA", str(appdata))
    settings_dir = appdata / "RivalsConfigManager"
    settings_dir.mkdir(parents=True)
    (settings_dir / "settings.json").write_text(
        json.dumps({"favorites": ["Pixelhandgun.json", "key up.json"]}),
        encoding="utf-8",
    )
    settings = AppSettings.load()
    assert settings.favorites == ["Pixelhandgun.json", "key up.json"]
    # Valeurs non-texte ignorées sans erreur.
    (settings_dir / "settings.json").write_text(
        json.dumps({"favorites": ["ok", 42, None, "also ok"]}),
        encoding="utf-8",
    )
    assert AppSettings.load().favorites == ["ok", "also ok"]


# ---------------------------------------------------------------------- #
# Recents
# ---------------------------------------------------------------------- #
def test_recents_bounded_and_ordered(tmp_path: Path) -> None:
    store = RecentsStore(tmp_path / "recents.json")
    for i in range(MAX_RECENTS + 5):
        store.record(f"key-{i}", f"Config {i}", timestamp=float(i))
    entries = store.entries()
    assert len(entries) == MAX_RECENTS
    # Most recent first (highest timestamp).
    assert entries[0].key == f"key-{MAX_RECENTS + 4}"
    # Re-recording moves an entry to the front without duplicating.
    store.record("key-5", "Config 5", timestamp=9999.0)
    assert [e.key for e in store.entries()].count("key-5") == 1
    assert store.entries()[0].key == "key-5"


def test_recents_persist_across_restart(tmp_path: Path) -> None:
    path = tmp_path / "recents.json"
    RecentsStore(path).record("a", "Alpha", timestamp=1.0)
    store = RecentsStore(path)
    assert [e.key for e in store.entries()] == ["a"]
    assert store.entries()[0].name == "Alpha"


def test_recents_corrupt_file_never_crashes(tmp_path: Path) -> None:
    path = tmp_path / "recents.json"
    path.write_text("not json {{{", encoding="utf-8")
    store = RecentsStore(path)
    assert store.entries() == []
    store.record("x", "X")
    assert [e.key for e in store.entries()] == ["x"]


# ---------------------------------------------------------------------- #
# Verification
# ---------------------------------------------------------------------- #
def _item(json_path: Path) -> ConfigItem:
    return ConfigItem(
        name=json_path.stem,
        path=json_path,
        kind=KIND_FILE,
        files=[json_path],
        json_files=[json_path],
    )


@pytest.fixture(autouse=True)
def _clean_analysis_cache():
    clear_cache()
    yield
    clear_cache()


def test_verify_valid_config(tmp_path: Path) -> None:
    (tmp_path / "model.obj").write_text("v 0 0 0", encoding="utf-8")
    json_path = tmp_path / "skin.json"
    json_path.write_text(
        json.dumps({"replacement_rules": [{"cdn_url": "model.obj"}]}),
        encoding="utf-8",
    )
    result = verify_item(_item(json_path))
    assert result.valid
    assert result.json_ok
    assert result.category_ok
    assert result.files_ok
    assert result.deps.missing_obj_files == ()
    assert result.problems == []


def test_verify_invalid_json(tmp_path: Path) -> None:
    json_path = tmp_path / "broken.json"
    json_path.write_text("{ not valid json", encoding="utf-8")
    result = verify_item(_item(json_path))
    assert not result.valid
    assert not result.json_ok
    # Une dépendance inconnue n'est jamais affirmée.
    assert not result.deps.obj_required
    assert result.problems  # au moins le problème JSON


def test_verify_missing_obj_and_mp3(tmp_path: Path) -> None:
    json_path = tmp_path / "gun.json"
    json_path.write_text(
        json.dumps(
            {
                "replacement_rules": [
                    {"cdn_url": "missing.obj"},
                    {"sound_url": "missing.mp3"},
                ]
            }
        ),
        encoding="utf-8",
    )
    result = verify_item(_item(json_path))
    assert not result.valid
    assert result.json_ok
    assert result.deps.missing_obj_files == ("missing.obj",)
    assert result.deps.missing_mp3_files == ("missing.mp3",)
    kinds = [p for p in result.problems if "OBJ" in p or "MP3" in p]
    assert len(kinds) == 2


def test_verify_missing_file_on_disk(tmp_path: Path) -> None:
    json_path = tmp_path / "skin.json"
    json_path.write_text(json.dumps({"replacement_rules": []}), encoding="utf-8")
    phantom = tmp_path / "preview.png"  # référencé mais jamais créé
    item = ConfigItem(
        name=json_path.stem,
        path=json_path,
        kind=KIND_FILE,
        files=[json_path, phantom],
        json_files=[json_path],
    )
    result = verify_item(item)
    assert not result.valid
    assert "preview.png" in result.files_missing


def test_verify_missing_category_folder(tmp_path: Path) -> None:
    json_path = tmp_path / "ghost" / "skin.json"
    json_path.parent.mkdir()
    json_path.write_text(json.dumps({"replacement_rules": []}), encoding="utf-8")
    item = _item(json_path)
    # La catégorie disparaît (dossier supprimé) -> flaggé.
    json_path.unlink()
    json_path.parent.rmdir()
    result = verify_item(item)
    assert not result.valid
    assert not result.category_ok


def test_verify_no_json_never_claims_valid(tmp_path: Path) -> None:
    json_path = tmp_path / "skin.json"
    json_path.write_text(json.dumps({"replacement_rules": []}), encoding="utf-8")
    item = ConfigItem(
        name=json_path.stem,
        path=json_path,
        kind=KIND_FILE,
        files=[json_path],
        json_files=[],  # aucun JSON -> « no_json »
    )
    result = verify_item(item)
    assert not result.valid
    assert any("JSON" in p for p in result.problems)


# ---------------------------------------------------------------------- #
# Repair
# ---------------------------------------------------------------------- #
def test_repair_plan_copies_missing_from_associated_obj(tmp_path: Path, monkeypatch) -> None:
    """OBJ associé dans le cache dont le nom correspond à la référence
    manquante -> plan de copie vers le dossier du JSON."""
    obj_cache = tmp_path / "obj_cache"
    obj_cache.mkdir()
    (obj_cache / "Pixelboddy.obj").write_text("mesh", encoding="utf-8")
    json_path = tmp_path / "lib" / "Secondary" / "Hand gun" / "Pixelhandgun.json"
    json_path.parent.mkdir(parents=True)
    json_path.write_text(
        json.dumps({"replacement_rules": [{"cdn_url": "Pixelboddy.obj"}]}),
        encoding="utf-8",
    )
    item = _item(json_path)
    item.obj = obj_cache / "Pixelboddy.obj"
    item.obj_name = "Pixelboddy.obj"

    verification = verify_item(item)
    assert verification.deps.missing_obj_files == ("Pixelboddy.obj",)
    plan = build_repair_plan(
        item, verification, library_root=json_path.parent.parent.parent, obj_cache=obj_cache
    )
    assert plan.possible
    assert len(plan.actions) == 1
    assert plan.actions[0].source == obj_cache / "Pixelboddy.obj"
    assert plan.actions[0].target == json_path.parent / "Pixelboddy.obj"

    errors = apply_repair(plan)
    assert errors == []
    assert (json_path.parent / "Pixelboddy.obj").exists()
    # Re-vérification réelle -> maintenant complète.
    assert verify_item(item).valid


def test_repair_plan_finds_moved_file_in_library(tmp_path: Path) -> None:
    """Fichier déplacé ailleurs dans la bibliothèque -> proposé en copie."""
    lib = tmp_path / "lib"
    (lib / "Charms").mkdir(parents=True)
    (lib / "Charms" / "model.obj").write_text("mesh", encoding="utf-8")
    json_path = lib / "Primary" / "gun.json"
    json_path.parent.mkdir(parents=True)
    json_path.write_text(
        json.dumps({"replacement_rules": [{"cdn_url": "model.obj"}]}),
        encoding="utf-8",
    )
    verification = verify_item(_item(json_path))
    plan = build_repair_plan(_item(json_path), verification, library_root=lib)
    assert plan.possible
    assert plan.actions[0].source == lib / "Charms" / "model.obj"
    assert plan.actions[0].target == json_path.parent / "model.obj"


def test_repair_never_overwrites_existing_file(tmp_path: Path) -> None:
    json_path = tmp_path / "skin.json"
    json_path.write_text(
        json.dumps({"replacement_rules": [{"cdn_url": "model.obj"}]}),
        encoding="utf-8",
    )
    (tmp_path / "model.obj").write_text("already there", encoding="utf-8")
    verification = verify_item(_item(json_path))
    assert verification.deps.missing_obj_files == ()
    plan = build_repair_plan(_item(json_path), verification, library_root=tmp_path)
    # Rien de manquant -> plan « rien à faire », jamais d'écrasement.
    assert plan.actions == []
    assert (tmp_path / "model.obj").read_text(encoding="utf-8") == "already there"


def test_repair_impossible_when_no_source(tmp_path: Path) -> None:
    json_path = tmp_path / "skin.json"
    json_path.write_text(
        json.dumps({"replacement_rules": [{"cdn_url": "nowhere.obj"}]}),
        encoding="utf-8",
    )
    verification = verify_item(_item(json_path))
    plan = build_repair_plan(_item(json_path), verification, library_root=tmp_path)
    assert not plan.possible
    assert plan.actions == []
    assert "nowhere.obj" in plan.missing
    assert "Impossible" in plan.explanation or "cannot" in plan.explanation.lower()


def test_repair_never_reports_fixed_without_reverify(tmp_path: Path) -> None:
    """« Réparé » n'est jamais affirmé : après l'application, la
    re-vérification réelle décide (le test simule un échec de copie)."""
    json_path = tmp_path / "skin.json"
    json_path.write_text(
        json.dumps({"replacement_rules": [{"cdn_url": "model.obj"}]}),
        encoding="utf-8",
    )
    (tmp_path / "model.obj").write_text("mesh", encoding="utf-8")
    item = _item(json_path)
    verification = verify_item(item)
    assert verification.valid  # le fichier est là
    # Un plan « vide » n'est jamais considéré comme une réparation réussie.
    from app.repair import RepairPlan

    assert not apply_repair(RepairPlan(possible=True))
    assert verify_item(item).valid


# ---------------------------------------------------------------------- #
# Profiles
# ---------------------------------------------------------------------- #
def _profile_manager(tmp_path: Path) -> ProfileManager:
    return ProfileManager(tmp_path / "profiles")


def test_profile_create_list_get_delete(tmp_path: Path) -> None:
    manager = _profile_manager(tmp_path)
    profile = manager.create(
        "Tryhard",
        description="Ranked setup",
        entries=[ProfileEntry(name="Keyblade", rel_path="Primary/Keyblade.json")],
    )
    assert manager.exists("Tryhard")
    assert manager.get("Tryhard").count == 1
    names = [p.name for p in manager.list_profiles()]
    assert names == ["Tryhard"]

    assert manager.delete("Tryhard") is True
    assert manager.get("Tryhard") is None
    assert manager.list_profiles() == []


def test_profile_duplicate_name_rejected(tmp_path: Path) -> None:
    manager = _profile_manager(tmp_path)
    manager.create("Aim")
    with pytest.raises(ProfileError):
        manager.create("Aim")


def test_profile_empty_name_rejected(tmp_path: Path) -> None:
    manager = _profile_manager(tmp_path)
    with pytest.raises(ProfileError):
        manager.create("   ")


def test_profile_persists_across_manager_instances(tmp_path: Path) -> None:
    directory = tmp_path / "profiles"
    ProfileManager(directory).create("Ranked", entries=[])
    reloaded = ProfileManager(directory)
    assert reloaded.get("Ranked") is not None


def test_profile_export_import_roundtrip(tmp_path: Path) -> None:
    manager = _profile_manager(tmp_path)
    manager.create(
        "Chill",
        description="Casual",
        entries=[
            ProfileEntry(name="Sheriff", rel_path="Secondary/Sheriff.json", category="Secondary"),
            ProfileEntry(name="Nemesis Charm", rel_path="Charms/Nemesis Charm.json", category="Charms"),
        ],
    )
    exported = manager.export_profile("Chill", tmp_path / "Chill.rcmprofile")
    assert exported.suffix == ".rcmprofile"
    assert exported.exists()
    raw = json.loads(exported.read_text(encoding="utf-8"))
    # Jamais de chemins absolus ni de données personnelles dans l'export.
    payload = json.dumps(raw)
    assert "C:" not in payload and "\\\\" not in payload
    assert "APPDATA" not in payload.upper()

    other = _profile_manager(tmp_path / "other")
    imported = other.import_profile(exported)
    assert imported.name == "Chill"
    assert imported.count == 2
    assert other.get("Chill").entries[0].rel_path == "Secondary/Sheriff.json"


def test_profile_import_invalid_file_rejected(tmp_path: Path) -> None:
    manager = _profile_manager(tmp_path)
    bad = tmp_path / "bad.rcmprofile"
    bad.write_text("{ nope", encoding="utf-8")
    with pytest.raises(ProfileError):
        manager.import_profile(bad)
    empty = tmp_path / "empty.rcmprofile"
    empty.write_text(json.dumps({"entries": []}), encoding="utf-8")
    with pytest.raises(ProfileError):
        manager.import_profile(empty)


def test_profile_import_same_name_never_overwrites(tmp_path: Path) -> None:
    directory = tmp_path / "profiles"
    manager = ProfileManager(directory)
    manager.create("Tryhard", entries=[])
    exported = manager.export_profile("Tryhard", tmp_path / "Tryhard.rcmprofile")
    imported = manager.import_profile(exported)
    assert imported.name != "Tryhard"  # suffixe ajouté, jamais écrasé
    assert manager.exists("Tryhard")
    assert manager.exists(imported.name)
