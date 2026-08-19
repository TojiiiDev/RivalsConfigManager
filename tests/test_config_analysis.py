"""Tests for app/config_analysis.py (OBJ + MP3 dependency detection).

The detection rules were derived from inspecting the real library (360+
JSONs): meshes are referenced by ``replacement_rules[].cdn_url`` and sounds
by ``sound_url``/``cdn_url`` — full URLs are remote (no local file needed,
never flagged), bare names / local paths ending in ``.obj`` / ``.mp3``
(case-insensitive) are local dependencies checked next to the JSON. Since
1.2.0 OBJ and MP3 are analysed independently (ConfigDependencies).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from app.config_analysis import (
    ObjAnalysis,
    analyze_config,
    analyze_item,
    cache_size,
    clear_cache,
)
from app.models import KIND_FILE, ConfigItem


def _write(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _item(json_path: Path) -> ConfigItem:
    return ConfigItem(
        name=json_path.stem,
        path=json_path,
        kind=KIND_FILE,
        files=[json_path],
        json_files=[json_path],
    )


@pytest.fixture(autouse=True)
def _clean_cache():
    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------------- #
# 1. JSON sans OBJ
# ---------------------------------------------------------------------- #
def test_json_without_obj_requires_nothing(tmp_path: Path) -> None:
    json_path = tmp_path / "skin.json"
    _write(json_path, {"replacement_rules": [{"mode": "id", "replace_ids": [1]}]})
    analysis = analyze_config(json_path)
    assert analysis.valid
    assert not analysis.obj_required
    assert analysis.obj_files == ()
    assert analysis.missing_obj_files == ()


# ---------------------------------------------------------------------- #
# 2 & 3. OBJ requis et présent
# ---------------------------------------------------------------------- #
def test_obj_required_and_present(tmp_path: Path) -> None:
    (tmp_path / "Pixelhandgun.obj").write_text("v 0 0 0", encoding="utf-8")
    json_path = tmp_path / "Pixelhandgun.json"
    _write(
        json_path,
        {"replacement_rules": [{"mode": "cdn", "cdn_url": "Pixelhandgun.obj"}]},
    )
    analysis = analyze_config(json_path)
    assert analysis.valid
    assert analysis.obj_required
    assert analysis.obj_files == ("Pixelhandgun.obj",)
    assert analysis.present_obj_files == ("Pixelhandgun.obj",)
    assert analysis.missing_obj_files == ()
    assert not analysis.incomplete


# ---------------------------------------------------------------------- #
# 4. OBJ requis mais absent
# ---------------------------------------------------------------------- #
def test_obj_required_but_missing(tmp_path: Path) -> None:
    json_path = tmp_path / "Pixelhandgun.json"
    _write(
        json_path,
        {"replacement_rules": [{"mode": "cdn", "cdn_url": "Pixelhandgun.obj"}]},
    )
    analysis = analyze_config(json_path)
    assert analysis.valid
    assert analysis.obj_required
    assert analysis.obj_files == ("Pixelhandgun.obj",)
    assert analysis.present_obj_files == ()
    assert analysis.missing_obj_files == ("Pixelhandgun.obj",)
    assert analysis.incomplete


# ---------------------------------------------------------------------- #
# 5. Plusieurs OBJ
# ---------------------------------------------------------------------- #
def test_multiple_objs_are_listed_individually(tmp_path: Path) -> None:
    (tmp_path / "Weapon.obj").write_text("v 0 0 0", encoding="utf-8")
    json_path = tmp_path / "gun.json"
    _write(
        json_path,
        {
            "replacement_rules": [
                {"cdn_url": "Weapon.obj"},
                {"cdn_url": "Body.obj"},
                {"cdn_url": "Weapon.obj"},  # doublon ignoré
            ]
        },
    )
    analysis = analyze_config(json_path)
    assert analysis.obj_required
    assert analysis.obj_files == ("Body.obj", "Weapon.obj")
    assert analysis.present_obj_files == ("Weapon.obj",)
    assert analysis.missing_obj_files == ("Body.obj",)
    assert analysis.incomplete


# ---------------------------------------------------------------------- #
# 6. JSON invalide
# ---------------------------------------------------------------------- #
def test_invalid_json_is_flagged_not_guessed(tmp_path: Path) -> None:
    json_path = tmp_path / "broken.json"
    json_path.write_text("{ pas du json", encoding="utf-8")
    analysis = analyze_config(json_path)
    assert not analysis.valid
    assert not analysis.obj_required
    assert analysis.missing_obj_files == ()


def test_missing_file_never_raises(tmp_path: Path) -> None:
    analysis = analyze_config(tmp_path / "ghost.json")
    assert not analysis.valid


# ---------------------------------------------------------------------- #
# 7. Structure inattendue
# ---------------------------------------------------------------------- #
def test_unexpected_structure_is_safe(tmp_path: Path) -> None:
    # Un JSON qui n'est pas un objet (liste) : dépendances inconnues.
    json_path = tmp_path / "weird.json"
    json_path.write_text('["a.obj", "b.obj"]', encoding="utf-8")
    analysis = analyze_config(json_path)
    assert not analysis.valid
    assert not analysis.obj_required


# ---------------------------------------------------------------------- #
# 8. Faux positifs potentiels
# ---------------------------------------------------------------------- #
def test_remote_url_obj_is_not_a_local_dependency(tmp_path: Path) -> None:
    """Une cdn_url complète (https://…x.obj) est téléchargée par Fleasion :
    aucun fichier local requis — jamais signalée comme manquante."""
    json_path = tmp_path / "charm.json"
    _write(
        json_path,
        {
            "replacement_rules": [
                {
                    "mode": "cdn",
                    "cdn_url": "https://github.com/user/repo/raw/main/symbol.obj",
                }
            ]
        },
    )
    analysis = analyze_config(json_path)
    assert analysis.valid
    assert not analysis.obj_required, "une URL distante ne doit pas créer de dépendance locale"
    assert analysis.missing_obj_files == ()


def test_obj_mention_mid_sentence_is_not_a_reference(tmp_path: Path) -> None:
    json_path = tmp_path / "skin.json"
    _write(
        json_path,
        {
            "replacement_rules": [],
            "description": "ce mod utilise des fichiers .obj pour le modèle",
        },
    )
    analysis = analyze_config(json_path)
    assert analysis.valid
    assert not analysis.obj_required


def test_local_path_with_subfolders_uses_basename(tmp_path: Path) -> None:
    """« clan/rivals/obj/x.obj » référence le fichier local x.obj."""
    (tmp_path / "Sheriffmag.obj").write_text("v 0 0 0", encoding="utf-8")
    json_path = tmp_path / "sheriff.json"
    _write(
        json_path,
        {"replacement_rules": [{"cdn_url": "clan/rivals/obj/revolver/sheriff/Sheriffmag.obj"}]},
    )
    analysis = analyze_config(json_path)
    assert analysis.obj_required
    assert analysis.obj_files == ("Sheriffmag.obj",)
    assert analysis.missing_obj_files == ()
    assert analysis.present_obj_files == ("Sheriffmag.obj",)


# ---------------------------------------------------------------------- #
# 9. Analyse récursive (le format réel imbrique les règles)
# ---------------------------------------------------------------------- #
def test_recursive_scan_finds_nested_references(tmp_path: Path) -> None:
    """Le vrai format utilise replacement_rules[] ; on scanne récursivement
    toutes les chaînes, y compris profondément imbriquées."""
    (tmp_path / "base.obj").write_text("v 0 0 0", encoding="utf-8")
    json_path = tmp_path / "deep.json"
    _write(
        json_path,
        {
            "replacement_rules": [
                {
                    "name": "x",
                    "nested": {"deep": {"deeper": ["a.obj", "base.obj"]}},
                    "cdn_url": "https://remote.example/x.obj",
                }
            ]
        },
    )
    analysis = analyze_config(json_path)
    assert analysis.obj_required
    assert analysis.obj_files == ("a.obj", "base.obj")
    assert analysis.missing_obj_files == ("a.obj",)
    assert analysis.present_obj_files == ("base.obj",)


def test_folder_configuration_merges_all_jsons(tmp_path: Path) -> None:
    (tmp_path / "A.obj").write_text("v 0 0 0", encoding="utf-8")
    _write(tmp_path / "config.json", {"replacement_rules": [{"cdn_url": "A.obj"}]})
    _write(tmp_path / "extra.json", {"replacement_rules": [{"cdn_url": "Missing.obj"}]})
    analysis = analyze_config(tmp_path)
    assert analysis.obj_required
    assert analysis.obj_files == ("A.obj", "Missing.obj")
    assert analysis.present_obj_files == ("A.obj",)
    assert analysis.missing_obj_files == ("Missing.obj",)


def test_analyze_item_uses_item_json_files(tmp_path: Path) -> None:
    (tmp_path / "X.obj").write_text("v 0 0 0", encoding="utf-8")
    json_path = tmp_path / "skin.json"
    _write(json_path, {"replacement_rules": [{"cdn_url": "X.obj"}]})
    analysis = analyze_item(_item(json_path))
    assert analysis.obj_required
    assert analysis.present_obj_files == ("X.obj",)


# ---------------------------------------------------------------------- #
# 10. Performance / cache
# ---------------------------------------------------------------------- #
def test_cache_reuses_parses_and_clears(tmp_path: Path) -> None:
    json_path = tmp_path / "skin.json"
    _write(json_path, {"replacement_rules": [{"cdn_url": "Gone.obj"}]})

    analyze_config(json_path)
    assert cache_size() == 1
    before = cache_size()
    # Deuxième analyse : rejouée depuis le cache (parseur non ré-exécuté).
    analyze_config(json_path)
    assert cache_size() == before

    clear_cache()
    assert cache_size() == 0
    analyze_config(json_path)
    assert cache_size() == 1


def test_cache_invalidated_when_file_changes(tmp_path: Path) -> None:
    json_path = tmp_path / "skin.json"
    _write(json_path, {"replacement_rules": [{"cdn_url": "Gone.obj"}]})
    assert analyze_config(json_path).missing_obj_files == ("Gone.obj",)

    time.sleep(0.01)
    _write(json_path, {"replacement_rules": []})
    # Le mtime a changé : le cache est invalidé, la nouvelle analyse est à jour.
    analysis = analyze_config(json_path)
    assert not analysis.obj_required


def test_obj_presence_is_always_fresh(tmp_path: Path) -> None:
    """L'existence des fichiers n'est JAMAIS mise en cache : importer le
    mesh manquant après une analyse est reflété immédiatement."""
    json_path = tmp_path / "skin.json"
    _write(json_path, {"replacement_rules": [{"cdn_url": "Mesh.obj"}]})
    analysis = analyze_config(json_path)
    assert analysis.missing_obj_files == ("Mesh.obj",)

    (tmp_path / "Mesh.obj").write_text("v 0 0 0", encoding="utf-8")
    analysis = analyze_config(json_path)  # même cache de parsing, existence fraîche
    assert analysis.missing_obj_files == ()
    assert analysis.present_obj_files == ("Mesh.obj",)


# ====================================================================== #
# 1.2.0 — analyse des dépendances MP3 (indépendante de l'analyse OBJ)
# ====================================================================== #
def test_mp3_required_and_present(tmp_path: Path) -> None:
    (tmp_path / "Pixelhandgun.mp3").write_bytes(b"ID3")
    json_path = tmp_path / "Pixelhandgun.json"
    _write(
        json_path,
        {"replacement_rules": [{"sound_url": "Pixelhandgun.mp3"}]},
    )
    analysis = analyze_config(json_path)
    assert analysis.valid
    assert analysis.mp3_required
    assert analysis.mp3_files == ("Pixelhandgun.mp3",)
    assert analysis.present_mp3_files == ("Pixelhandgun.mp3",)
    assert analysis.missing_mp3_files == ()
    assert not analysis.incomplete
    # L'OBJ n'est pas affecté : la config ne référence aucun OBJ.
    assert not analysis.obj_required


def test_mp3_required_but_missing(tmp_path: Path) -> None:
    json_path = tmp_path / "Pixelhandgun.json"
    _write(
        json_path,
        {"replacement_rules": [{"sound_url": "Pixelhandgun.mp3"}]},
    )
    analysis = analyze_config(json_path)
    assert analysis.valid
    assert analysis.mp3_required
    assert analysis.present_mp3_files == ()
    assert analysis.missing_mp3_files == ("Pixelhandgun.mp3",)
    assert analysis.incomplete


def test_multiple_mp3s_are_listed_individually(tmp_path: Path) -> None:
    (tmp_path / "theme.mp3").write_bytes(b"ID3")
    json_path = tmp_path / "gun.json"
    _write(
        json_path,
        {
            "replacement_rules": [
                {"sound_url": "theme.mp3"},
                {"sound_url": "voice.mp3"},
            ]
        },
    )
    analysis = analyze_config(json_path)
    assert analysis.mp3_required
    assert analysis.mp3_files == ("theme.mp3", "voice.mp3")
    assert analysis.present_mp3_files == ("theme.mp3",)
    assert analysis.missing_mp3_files == ("voice.mp3",)
    assert analysis.incomplete


def test_obj_and_mp3_dependencies_are_separate(tmp_path: Path) -> None:
    (tmp_path / "Body.obj").write_text("v 0 0 0", encoding="utf-8")
    (tmp_path / "Body.mp3").write_bytes(b"ID3")
    json_path = tmp_path / "combo.json"
    _write(
        json_path,
        {
            "replacement_rules": [
                {"cdn_url": "Body.obj"},
                {"sound_url": "Body.mp3"},
            ]
        },
    )
    analysis = analyze_config(json_path)
    assert analysis.obj_required and analysis.mp3_required
    assert analysis.present_obj_files == ("Body.obj",)
    assert analysis.present_mp3_files == ("Body.mp3",)
    assert analysis.missing_obj_files == ()
    assert analysis.missing_mp3_files == ()
    assert not analysis.incomplete


def test_remote_mp3_url_is_not_a_local_dependency(tmp_path: Path) -> None:
    """Une sound_url complète (https://…) est téléchargée par Fleasion :
    aucun fichier local requis — jamais signalée comme manquante."""
    json_path = tmp_path / "sound.json"
    _write(
        json_path,
        {
            "replacement_rules": [
                {"sound_url": "https://cdn.example.com/audio/theme.mp3"}
            ]
        },
    )
    analysis = analyze_config(json_path)
    assert analysis.valid
    assert not analysis.mp3_required
    assert analysis.missing_mp3_files == ()


def test_dangerous_mp3_paths_never_escape_the_config_folder(tmp_path: Path) -> None:
    """« ../evil.mp3 » et un chemin absolu ne sont JAMAIS suivis : seul le
    nom de fichier est résolu à côté du JSON."""
    sub = tmp_path / "sub"
    sub.mkdir()
    # Un fichier qui existerait à l'endroit pointé par « ../evil.mp3 »…
    (tmp_path / "evil.mp3").write_bytes(b"ID3")
    (tmp_path / "evil.obj").write_text("v 0 0 0", encoding="utf-8")
    json_path = sub / "skin.json"
    _write(
        json_path,
        {
            "replacement_rules": [
                {"sound_url": "../evil.mp3"},
                {"cdn_url": "C:/Windows/system.obj"},
            ]
        },
    )
    analysis = analyze_config(json_path)
    # Les références sont retenues (noms de fichiers)…
    assert analysis.mp3_files == ("evil.mp3",)
    assert analysis.obj_files == ("system.obj",)
    # …mais résolues UNIQUEMENT à côté du JSON : ni l'une ni l'autre ne
    # « existe » (pas de fuite hors du dossier de configuration).
    assert analysis.present_mp3_files == ()
    assert analysis.missing_mp3_files == ("evil.mp3",)
    assert analysis.missing_obj_files == ("system.obj",)


def test_mp3_references_are_deduplicated(tmp_path: Path) -> None:
    (tmp_path / "loop.mp3").write_bytes(b"ID3")
    json_path = tmp_path / "song.json"
    _write(
        json_path,
        {
            "replacement_rules": [
                {"sound_url": "loop.mp3"},
                {"sound_url": "loop.mp3"},
                {"another": ["loop.mp3"]},
            ]
        },
    )
    analysis = analyze_config(json_path)
    assert analysis.mp3_files == ("loop.mp3",)  # dédupliqué, pas 3 entrées
    assert analysis.present_mp3_files == ("loop.mp3",)


def test_nested_mp3_references_are_found(tmp_path: Path) -> None:
    (tmp_path / "ambience.mp3").write_bytes(b"ID3")
    json_path = tmp_path / "deep.json"
    _write(
        json_path,
        {
            "replacement_rules": [
                {"audio": {"layers": [{"file": "ambience.mp3"}, "gone.mp3"]}}
            ]
        },
    )
    analysis = analyze_config(json_path)
    assert analysis.mp3_required
    assert analysis.mp3_files == ("ambience.mp3", "gone.mp3")
    assert analysis.present_mp3_files == ("ambience.mp3",)
    assert analysis.missing_mp3_files == ("gone.mp3",)


def test_mp3_resolution_matches_library_convention(tmp_path: Path) -> None:
    """Convention réelle de la bibliothèque : extension .MP3 majuscule,
    fichier à côté du JSON, résolution insensible à la casse."""
    (tmp_path / "Keylaws sound 1.MP3").write_bytes(b"ID3")
    json_path = tmp_path / "keylaws.json"
    _write(
        json_path,
        {
            "replacement_rules": [
                {"sound_url": "C:/mesh/Keylaws sound 1.MP3"}
            ]
        },
    )
    analysis = analyze_config(json_path)
    assert analysis.mp3_required
    assert analysis.mp3_files == ("Keylaws sound 1.MP3",)
    assert analysis.present_mp3_files == ("Keylaws sound 1.MP3",)


def test_mp3_presence_is_always_fresh(tmp_path: Path) -> None:
    """Comme pour l'OBJ : l'existence du MP3 n'est jamais mise en cache."""
    json_path = tmp_path / "skin.json"
    _write(json_path, {"replacement_rules": [{"sound_url": "Music.mp3"}]})
    assert analyze_config(json_path).missing_mp3_files == ("Music.mp3",)

    (tmp_path / "Music.mp3").write_bytes(b"ID3")
    analysis = analyze_config(json_path)  # même cache de parsing, existence fraîche
    assert analysis.missing_mp3_files == ()
    assert analysis.present_mp3_files == ("Music.mp3",)


def test_config_dependencies_alias_backwards_compatible() -> None:
    """ObjAnalysis (nom 1.1.0) reste un alias de ConfigDependencies."""
    from app.config_analysis import ConfigDependencies

    assert ObjAnalysis is ConfigDependencies


# ====================================================================== #
# 1.3.1 — l'absence ne prouve jamais qu'un fichier est requis : seule la
# structure réelle de Fleasion (replacement_rules actifs) crée une
# dépendance explicite.
# ====================================================================== #
def test_string_outside_replacement_rules_is_never_required(tmp_path: Path) -> None:
    """Un texte finissant par .mp3/.obj hors de replacement_rules (métadonnée,
    nom, description, with_id) ne crée JAMAIS de dépendance : « Tier 8 » ne
    doit pas être signalé « MP3 requis » à cause d'une chaîne parasite."""
    (tmp_path / "tier 8 sound.mp3").write_bytes(b"ID3")
    json_path = tmp_path / "tier8.json"
    _write(
        json_path,
        {
            "replacement_rules": [
                {"name": "hit sound", "mode": "id", "with_id": 123456, "enabled": True}
            ],
            "note": "tier 8 sound.mp3 fourni par le créateur",
            "stale_path": "C:/Users/creator/Downloads/tier 8 sound.mp3",
        },
    )
    analysis = analyze_config(json_path)
    assert analysis.valid
    assert not analysis.mp3_required
    assert not analysis.obj_required
    assert analysis.missing_mp3_files == ()
    assert not analysis.incomplete


def test_disabled_rule_never_creates_a_requirement(tmp_path: Path) -> None:
    """Une règle désactivée (enabled: false) est ignorée par Fleasion : son
    local_path restant ne doit jamais être signalé « requis »."""
    json_path = tmp_path / "skin.json"
    _write(
        json_path,
        {
            "replacement_rules": [
                {
                    "name": "sound",
                    "mode": "local",
                    "enabled": False,
                    "local_path": "C:/Users/creator/Downloads/tier 8 sound.mp3",
                }
            ]
        },
    )
    analysis = analyze_config(json_path)
    assert analysis.valid
    assert not analysis.mp3_required
    assert analysis.missing_mp3_files == ()


def test_active_and_disabled_rules_are_independent(tmp_path: Path) -> None:
    """Une règle active + une règle désactivée : seule l'active compte."""
    (tmp_path / "real.mp3").write_bytes(b"ID3")
    json_path = tmp_path / "combo.json"
    _write(
        json_path,
        {
            "replacement_rules": [
                {"mode": "local", "enabled": True, "local_path": "C:/mesh/real.mp3"},
                {"mode": "local", "enabled": False, "local_path": "C:/mesh/gone.mp3"},
            ]
        },
    )
    analysis = analyze_config(json_path)
    assert analysis.mp3_required
    assert analysis.mp3_files == ("real.mp3",)
    assert analysis.present_mp3_files == ("real.mp3",)
    assert analysis.missing_mp3_files == ()


def test_sidecar_metadata_is_never_a_dependency(tmp_path: Path) -> None:
    """Les sidecars (.obj.json) portent source/local_path/file_name au niveau
    racine, hors replacement_rules : ce sont des métadonnées d'interface,
    jamais des dépendances de la configuration."""
    json_path = tmp_path / "skin.obj.json"
    _write(
        json_path,
        {
            "source": r"C:\Users\me\Desktop\skin.obj",
            "local_path": "obj_cache/12b9d7e24fe01f3d.obj",
            "file_name": "skin.obj",
        },
    )
    analysis = analyze_config(json_path)
    assert analysis.valid
    assert not analysis.obj_required
    assert not analysis.mp3_required
    assert analysis.missing_obj_files == ()


def test_disabled_child_rule_is_skipped(tmp_path: Path) -> None:
    """Les règles imbriquées (children) héritent de leur propre enabled :
    un enfant désactivé ne crée pas de dépendance."""
    (tmp_path / "keep.obj").write_text("v 0 0 0", encoding="utf-8")
    json_path = tmp_path / "deep.json"
    _write(
        json_path,
        {
            "replacement_rules": [
                {
                    "name": "parent",
                    "mode": "local",
                    "enabled": True,
                    "children": [
                        {"mode": "local", "enabled": True, "local_path": "keep.obj"},
                        {"mode": "local", "enabled": False, "local_path": "drop.obj"},
                    ],
                }
            ]
        },
    )
    analysis = analyze_config(json_path)
    assert analysis.obj_required
    assert analysis.obj_files == ("keep.obj",)
    assert analysis.present_obj_files == ("keep.obj",)
    assert analysis.missing_obj_files == ()


def test_real_format_mode_local_local_path(tmp_path: Path) -> None:
    """Le format réel de la bibliothèque : mode « local » + local_path avec
    un chemin absolu d'une autre machine — le nom de fichier est la
    dépendance, résolue à côté du JSON."""
    (tmp_path / "Keylaws sound 1.MP3").write_bytes(b"ID3")
    (tmp_path / "Keyrgy Pistols1.obj").write_text("v 0 0 0", encoding="utf-8")
    json_path = tmp_path / "Keyrgy Pistols.json"
    _write(
        json_path,
        {
            "replacement_rules": [
                {"name": "Body", "mode": "local", "enabled": True,
                 "local_path": "C:/mesh/Keyrgy Pistols1.obj"},
                {"name": "Shootsound", "mode": "local", "enabled": True,
                 "local_path": "C:/mesh/Keylaws sound 1.MP3"},
                {"name": "icon", "mode": "local", "enabled": True,
                 "local_path": "C:/mesh/icon.png"},
            ]
        },
    )
    analysis = analyze_config(json_path)
    assert analysis.obj_required and analysis.mp3_required
    assert analysis.obj_files == ("Keyrgy Pistols1.obj",)
    assert analysis.present_obj_files == ("Keyrgy Pistols1.obj",)
    assert analysis.mp3_files == ("Keylaws sound 1.MP3",)
    assert analysis.present_mp3_files == ("Keylaws sound 1.MP3",)
    assert not analysis.incomplete
