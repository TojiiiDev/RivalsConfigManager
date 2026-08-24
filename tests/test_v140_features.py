"""v1.3.11 — Phase 4 : import en masse (tri individuel) + profils en .zip.

Batch import:

* plusieurs sources (fichiers / dossiers / ZIP) analysées ensemble ;
* un ZIP contenant plusieurs mods est découpé en un élément par mod ;
* détection automatique (structure réelle de la bibliothèque / registre
  connu) — jamais une catégorie inventée, jamais de nom codé en dur ;
* tri individuel : chaque élément a sa propre destination, indépendante ;
* destination inconnue → « à choisir », import impossible tant qu'elle
  n'est pas choisie (aucune catégorie fantôme à l'installation) ;
* une erreur sur un élément n'empêche pas le reste du lot ;
* un seul élément garde le flux individuel existant ;
* persistance après redémarrage.

Profiles:

* export .zip (manifeste profile.json, références logiques, aucun chemin
  absolu) ; import validé ; fichiers non-profils refusés ; conflit de nom
  (copie / remplacement) ; export → import → comparaison ; persistance.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QDialog

from app.batch_import import analyze_batch, cleanup_batch
from app.profiles import ProfileEntry, ProfileError, ProfileManager


# ---------------------------------------------------------------------- #
# Fixtures / helpers
# ---------------------------------------------------------------------- #
@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _make_zip(path: Path, entries: dict[str, str]) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        for rel, content in entries.items():
            zf.writestr(rel, content)


def _library(tmp_path: Path) -> Path:
    """Realistic library: nested weapon categories + a flat category."""
    lib = tmp_path / "lib"
    _write_json(lib / "Charms" / "nemesis charm.json", {"replacement_rules": []})
    _write_json(
        lib / "rivals skins" / "Primary" / "Assault Rifle" / "ak-47.json",
        {"replacement_rules": []},
    )
    # Shotgun est détectée via le registre d'armes connu (même sans le dossier
    # dans la bibliothèque). Ne pas pré-créer le dossier vide évite une
    # collision avec MODE_KEEP_BOTH lors de l'installation.
    _write_json(
        lib / "rivals skins" / "Melee" / "Katana" / "kirambit.json",
        {"replacement_rules": []},
    )
    return lib


def _configure_env(tmp_path: Path, monkeypatch, library: Path) -> Path:
    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    from app.config import AppSettings

    fleasion = tmp_path / "fleasion"
    fleasion.mkdir(parents=True, exist_ok=True)
    (fleasion / "settings.json").write_text("{}", encoding="utf-8")
    settings = AppSettings()
    settings.library_dir = library
    settings.fleasion_dir = fleasion
    settings.save()
    return appdata


def _window(qapp, tmp_path, monkeypatch):
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    lib = _library(tmp_path)
    _configure_env(tmp_path, monkeypatch, lib)
    window = MainWindow()
    window.show()
    qapp.processEvents()
    return window, lib


# ---------------------------------------------------------------------- #
# 1. Analyse du lot — sources multiples
# ---------------------------------------------------------------------- #
def test_batch_analyze_multiple_sources(tmp_path: Path) -> None:
    """Plusieurs fichiers + un dossier + un ZIP → chaque source devient un
    élément importable (le clic et le drag & drop partagent ce pipeline)."""
    _write_json(tmp_path / "mod1.json", {"replacement_rules": []})
    _write_json(tmp_path / "mod2.json", {"replacement_rules": []})
    (tmp_path / "folder mod").mkdir()
    _write_json(tmp_path / "folder mod" / "config.json", {"replacement_rules": []})
    _make_zip(tmp_path / "pack.zip", {"PackSkin/config.json": '{"replacement_rules": []}'})

    items, errors = analyze_batch(
        [tmp_path / "mod1.json", tmp_path / "mod2.json",
         tmp_path / "folder mod", tmp_path / "pack.zip"]
    )
    assert errors == []
    assert len(items) == 4
    names = {i.name for i in items}
    assert {"mod1", "mod2", "folder mod", "PackSkin"} <= names
    cleanup_batch(items)


def test_batch_missing_source_reports_error_and_continues(tmp_path: Path) -> None:
    """Un fichier introuvable est signalé sans bloquer le reste du lot."""
    _write_json(tmp_path / "ok.json", {"replacement_rules": []})
    items, errors = analyze_batch([tmp_path / "missing.zip", tmp_path / "ok.json"])
    assert len(errors) == 1 and "missing.zip" in errors[0]
    assert len(items) == 1 and items[0].name == "ok"
    cleanup_batch(items)


def test_batch_bad_zip_reports_error(tmp_path: Path) -> None:
    bad = tmp_path / "broken.zip"
    bad.write_bytes(b"not a zip at all")
    items, errors = analyze_batch([bad])
    assert items == [] and len(errors) == 1


def test_batch_zip_single_mod_stays_one_item(tmp_path: Path) -> None:
    """Un ZIP avec un seul mod (dossier unique) reste UN élément, comme
    l'import individuel — jamais découpé inutilement."""
    _make_zip(
        tmp_path / "Gunblade_Black_Skin.zip",
        {"Gunblade_Black_Skin/config.json": '{"replacement_rules": []}'},
    )
    items, errors = analyze_batch([tmp_path / "Gunblade_Black_Skin.zip"])
    assert errors == []
    assert len(items) == 1
    assert items[0].name == "Gunblade Black Skin"
    cleanup_batch(items)


def test_batch_zip_multi_mod_splits_into_items(tmp_path: Path) -> None:
    """Un ZIP contenant plusieurs mods indépendants est découpé : un élément
    par dossier (AK47 / Shotgun / Pad / Katana Skin)."""
    zip_path = tmp_path / "mods.zip"
    _make_zip(
        zip_path,
        {
            "AK47/config.json": '{"replacement_rules": []}',
            "Shotgun/config.json": '{"replacement_rules": []}',
            "Pad/config.json": '{"replacement_rules": []}',
            "Katana Skin/config.json": '{"replacement_rules": []}',
        },
    )
    items, errors = analyze_batch([zip_path])
    assert errors == []
    assert len(items) == 4
    names = {i.name for i in items}
    assert names == {"AK47", "Shotgun", "Pad", "Katana Skin"}
    # L'origine est rappelée pour chaque élément découpé.
    assert all(i.origin for i in items)
    assert all(i.analysis.staging is not None for i in items)  # staging partagé
    cleanup_batch(items)
    # Le staging a bien été nettoyé.
    for item in items:
        assert item.analysis.staging is None or not item.analysis.staging.exists()


def test_batch_zip_loose_config_files_split(tmp_path: Path) -> None:
    """Des .json à la racine d'un ZIP sont des configurations indépendantes ;
    les images seules ne sont jamais des éléments importables."""
    zip_path = tmp_path / "loose.zip"
    _make_zip(
        zip_path,
        {
            "a.json": '{"replacement_rules": []}',
            "b.json": '{"replacement_rules": []}',
            "preview.png": "x",
        },
    )
    items, errors = analyze_batch([zip_path])
    assert errors == []
    assert len(items) == 2
    assert {i.name for i in items} == {"a", "b"}
    cleanup_batch(items)


def test_batch_empty_zip_reports_error(tmp_path: Path) -> None:
    zip_path = tmp_path / "empty.zip"
    _make_zip(zip_path, {"preview.png": "x"})  # aucune configuration
    items, errors = analyze_batch([zip_path])
    assert items == [] and len(errors) == 1


# ---------------------------------------------------------------------- #
# 2. Détection automatique + destination inconnue
# ---------------------------------------------------------------------- #
def test_batch_detection_proposes_and_unknown_stays_open(tmp_path: Path) -> None:
    lib = _library(tmp_path)
    (tmp_path / "Assault Rifle Black Skin").mkdir()
    _write_json(tmp_path / "Assault Rifle Black Skin" / "config.json", {"replacement_rules": []})
    (tmp_path / "Katana Skin").mkdir()
    _write_json(tmp_path / "Katana Skin" / "config.json", {"replacement_rules": []})
    (tmp_path / "Super Cool Thing 2024").mkdir()
    _write_json(tmp_path / "Super Cool Thing 2024" / "config.json", {"replacement_rules": []})

    items, errors = analyze_batch(
        [tmp_path / "Assault Rifle Black Skin", tmp_path / "Katana Skin",
         tmp_path / "Super Cool Thing 2024"],
        library_root=lib,
    )
    assert errors == []
    by_name = {i.name: i for i in items}

    ar = by_name["Assault Rifle Black Skin"]
    assert ar.detected_category == "primary" and ar.detected_weapon == "Assault Rifle"
    assert ar.category == "primary" and ar.weapon == "Assault Rifle"

    katana = by_name["Katana Skin"]
    assert katana.detected_category == "melee" and katana.detected_weapon == "Katana"

    # Le suffixe version « 2024 » est retiré du NOM (suggest_name), pas de
    # la détection : l'élément reste bien « Super Cool Thing ».
    unknown = by_name["Super Cool Thing"]
    assert unknown.detected_category is None
    assert unknown.category is None  # jamais inventée : à choisir
    cleanup_batch(items)


def test_batch_detection_never_hardcoded_mod_names(tmp_path: Path) -> None:
    """Aucune exception pour un nom précis : un nom inconnu reste ouvert."""
    lib = _library(tmp_path)
    (tmp_path / "AK47").mkdir()
    _write_json(tmp_path / "AK47" / "config.json", {"replacement_rules": []})
    items, _ = analyze_batch([tmp_path / "AK47"], library_root=lib)
    item = items[0]
    assert item.category is None  # pas de « AK47 → Primary » codé en dur
    cleanup_batch(items)


# ---------------------------------------------------------------------- #
# 3. Interface de tri du lot
# ---------------------------------------------------------------------- #
def test_batch_dialog_rows_independent_and_validation(tmp_path: Path, qapp) -> None:
    """Chaque élément a sa propre destination ; changer une ligne ne touche
    jamais les autres ; tant qu'une destination est inconnue, l'import est
    bloqué ; après choix manuel, il s'active."""
    from ui.views.batch_import_dialog import BatchImportDialog

    lib = _library(tmp_path)
    (tmp_path / "Assault Rifle Black Skin").mkdir()
    _write_json(tmp_path / "Assault Rifle Black Skin" / "config.json", {"replacement_rules": []})
    (tmp_path / "Mystery Mod").mkdir()
    _write_json(tmp_path / "Mystery Mod" / "config.json", {"replacement_rules": []})

    items, errors = analyze_batch(
        [tmp_path / "Assault Rifle Black Skin", tmp_path / "Mystery Mod"],
        library_root=lib,
    )
    assert errors == []
    dialog = BatchImportDialog(items, lib)
    dialog.show()
    qapp.processEvents()

    # La ligne détectée est pré-remplie ; l'inconnue est sur « — Choisir — ».
    rows = {r._item.name: r for r in dialog._rows}
    ar_row = rows["Assault Rifle Black Skin"]
    unknown_row = rows["Mystery Mod"]
    assert ar_row._category.currentData() == "primary"
    assert ar_row._weapon.currentText() == "Assault Rifle"
    assert unknown_row._category.currentData() is None
    # Import bloqué tant qu'une destination est inconnue.
    assert not dialog._import_btn.isEnabled()

    # Choisir manuellement la catégorie de l'élément inconnu : l'import
    # s'active, et la ligne détectée n'a pas bougé.
    unknown_row._category.setCurrentIndex(unknown_row._category.findData("utility"))
    assert dialog._import_btn.isEnabled()
    assert ar_row._category.currentData() == "primary"

    # Changer la destination de l'élément détecté ne touche pas l'autre.
    ar_row._category.setCurrentIndex(ar_row._category.findData("secondary"))
    assert unknown_row._category.currentData() == "utility"

    dialog._import_btn.click()
    result = dialog.result_items()
    by_name = {i.name: i for i in result}
    assert by_name["Assault Rifle Black Skin"].category == "secondary"
    assert by_name["Mystery Mod"].category == "utility"
    dialog.close()
    cleanup_batch(items)


# ---------------------------------------------------------------------- #
# 4. Import du lot de bout en bout (fenêtre réelle)
# ---------------------------------------------------------------------- #
def test_batch_import_end_to_end(qapp, tmp_path, monkeypatch) -> None:
    """ZIP multi-mods déposé → tri individuel → une seule validation →
    chaque mod arrive à SA destination ; aucune catégorie fantôme ; le
    résultat persiste après redémarrage."""
    import app.mod_import as mod_import
    from ui.main_window import MainWindow
    from ui.views.batch_import_dialog import BatchImportDialog

    window, lib = _window(qapp, tmp_path, monkeypatch)

    def fake_staging_base():
        base = tmp_path / "staging"
        base.mkdir(parents=True, exist_ok=True)
        return base

    monkeypatch.setattr(mod_import, "_staging_base", fake_staging_base)

    zip_path = tmp_path / "mods.zip"
    _make_zip(
        zip_path,
        {
            "AK47/config.json": '{"replacement_rules": []}',
            "Shotgun/config.json": '{"replacement_rules": []}',
            "Pad/config.json": '{"replacement_rules": []}',
        },
    )

    def fake_exec(self):
        # Tri individuel : AK47 → Primary > Assault Rifle (manuelle),
        # Shotgun détectée (Primary > Shotgun), Pad → Utility.
        for row in self._rows:
            name = row._item.name
            if name == "AK47":
                row._category.setCurrentIndex(row._category.findData("primary"))
                # Choix réel DANS la liste (le sélecteur n'est pas éditable).
                idx = row._weapon.findText("Assault Rifle")
                assert idx >= 0
                row._weapon.setCurrentIndex(idx)
            elif name == "Pad":
                row._category.setCurrentIndex(row._category.findData("utility"))
        return QDialog.Accepted

    monkeypatch.setattr(BatchImportDialog, "exec", fake_exec)

    window._start_batch_import([zip_path])
    qapp.processEvents()

    # Destinations respectées exactement.
    assert (lib / "rivals skins" / "Primary" / "Assault Rifle" / "AK47" / "config.json").exists()
    assert (lib / "rivals skins" / "Primary" / "Shotgun" / "config.json").exists()
    assert (lib / "Utility" / "Pad" / "config.json").exists()
    # Aucune catégorie fantôme (pas de dossier « mods », « AK47 » à la
    # racine, ni de dossier de détection ratée).
    assert not (lib / "mods").exists()
    assert not (lib / "AK47").exists()
    assert not (lib / "Shotgun").exists()
    assert not (lib / "Pad").exists()
    # Staging nettoyé.
    assert [p.name for p in (tmp_path / "staging").iterdir()] == []
    # Persistance : une nouvelle fenêtre voit les mods installés.
    window2 = MainWindow()
    window2.show()
    qapp.processEvents()
    assert (lib / "rivals skins" / "Primary" / "Assault Rifle" / "AK47" / "config.json").exists()
    nodes = window2.root_node
    assert nodes is not None
    window2.close()
    window.close()


def test_batch_single_element_keeps_single_flow(qapp, tmp_path, monkeypatch) -> None:
    """Un seul élément déposé garde le flux individuel existant (popup
    ImportDialog), jamais le gestionnaire de lot."""
    import app.mod_import as mod_import
    from ui.main_window import MainWindow
    from ui.views.batch_import_dialog import BatchImportDialog
    from ui.views.import_dialog import ImportDialog

    window, lib = _window(qapp, tmp_path, monkeypatch)

    def fake_staging_base():
        base = tmp_path / "staging"
        base.mkdir(parents=True, exist_ok=True)
        return base

    monkeypatch.setattr(mod_import, "_staging_base", fake_staging_base)

    zip_path = tmp_path / "single.zip"
    _make_zip(zip_path, {"Gunblade_Black_Skin/config.json": '{"replacement_rules": []}'})

    opened = []
    monkeypatch.setattr(ImportDialog, "exec",
                        lambda self: (opened.append(self), QDialog.Accepted)[1])
    monkeypatch.setattr(BatchImportDialog, "exec",
                        lambda self: (_ for _ in ()).throw(AssertionError("lot ouvert !")))

    window._start_batch_import([zip_path])
    qapp.processEvents()
    assert opened, "l'élément unique doit passer par le popup individuel"
    assert (lib / "rivals skins" / "Melee" / "Gunblade" / "Gunblade Black Skin" /
            "config.json").exists()
    window.close()


def test_batch_install_reports_partial_failure(qapp, tmp_path, monkeypatch) -> None:
    """Une erreur sur un élément ne fait jamais échouer le lot en silence :
    le reste est installé et l'échec est signalé."""
    from ui.main_window import MainWindow
    from ui.views.batch_import_dialog import BatchImportDialog

    window, lib = _window(qapp, tmp_path, monkeypatch)
    _write_json(tmp_path / "good.json", {"replacement_rules": []})
    _write_json(tmp_path / "bad.json", {"replacement_rules": []})

    items, errors = analyze_batch([tmp_path / "good.json", tmp_path / "bad.json"],
                                  library_root=lib)
    assert errors == []
    for item in items:
        item.category = "primary"
    # « bad » échoue : son analyse pointe vers un fichier supprimé.
    bad = next(i for i in items if i.name == "bad")
    bad.analysis.files = [type(bad.analysis.files[0])("missing.json", 5)]

    window._install_batch(items)
    qapp.processEvents()
    # La catégorie canonique résout la VRAIE bibliothèque (rivals skins/Primary).
    assert (lib / "rivals skins" / "Primary" / "good" / "good.json").exists()
    bad_dest = lib / "rivals skins" / "Primary" / "bad"
    # « bad » a échoué : aucun de ses fichiers n'a été copié (le dossier
    # vide créé par l'installation ne compte pas).
    assert not (bad_dest / "missing.json").exists()
    assert [p for p in bad_dest.rglob("*") if p.is_file()] == []
    window.close()
    cleanup_batch(items)


# ---------------------------------------------------------------------- #
# 5. Profils — export / import .zip
# ---------------------------------------------------------------------- #
def _profile_manager(tmp_path: Path) -> ProfileManager:
    return ProfileManager(tmp_path / "profiles")


def test_profile_export_is_zip_manifest_no_absolute_paths(tmp_path: Path) -> None:
    """L'export est un vrai .zip contenant profile.json ; le manifeste ne
    contient AUCUN chemin absolu ni donnée personnelle."""
    manager = _profile_manager(tmp_path)
    manager.create(
        "Tryhard",
        description="Ranked",
        entries=[ProfileEntry(name="AK", rel_path="Primary/AK-47.json", category="Primary")],
    )
    exported = manager.export_profile("Tryhard", tmp_path / "Tryhard.zip")
    assert exported.suffix == ".zip"
    assert zipfile.is_zipfile(exported)
    with zipfile.ZipFile(exported) as zf:
        names = zf.namelist()
        assert "profile.json" in names
        raw = json.loads(zf.read("profile.json").decode("utf-8"))
    payload = json.dumps(raw)
    assert "C:" not in payload and "\\\\" not in payload
    assert "APPDATA" not in payload.upper()
    assert raw["name"] == "Tryhard" and raw["format"] == 1
    assert raw["entries"][0]["rel_path"] == "Primary/AK-47.json"
    assert "library" not in payload.lower()


def test_profile_export_import_roundtrip_equal(tmp_path: Path) -> None:
    """Export → import → le profil reconstruit correspond au profil A :
    nom, description et références logiques identiques."""
    manager = _profile_manager(tmp_path)
    manager.create(
        "A",
        description="Ma config",
        entries=[
            ProfileEntry(name="AK-47", rel_path="rivals skins/Primary/Assault Rifle/ak-47.json",
                         category="Primary"),
            ProfileEntry(name="Kirambit", rel_path="rivals skins/Melee/Katana/kirambit.json",
                         category="Melee"),
        ],
    )
    exported = manager.export_profile("A", tmp_path / "A.zip")

    other = _profile_manager(tmp_path / "other")
    imported = other.import_profile(exported)
    original = manager.get("A")
    assert imported.name == original.name
    assert imported.description == original.description
    assert [e.to_dict() for e in imported.entries] == [e.to_dict() for e in original.entries]
    assert other.get("A") is not None
    # Les références restent résolubles contre une bibliothèque.
    lib = _library(tmp_path)
    for entry in imported.entries:
        assert (lib / entry.rel_path).exists()


def test_profile_conflict_copy_and_replace(tmp_path: Path) -> None:
    """Conflit de nom : par défaut copie suffixée (jamais d'écrasement
    silencieux) ; « replace » écrase explicitement."""
    manager = _profile_manager(tmp_path)
    manager.create("Tryhard", entries=[ProfileEntry(name="old", rel_path="a.json")])
    exported = manager.export_profile("Tryhard", tmp_path / "Tryhard.zip")

    copied = manager.import_profile(exported)  # conflit → copie
    assert copied.name != "Tryhard"
    assert manager.exists("Tryhard")
    assert manager.exists(copied.name)

    replaced = manager.import_profile(exported, conflict="replace")
    assert replaced.name == "Tryhard"
    assert manager.get("Tryhard") is not None


def test_profile_invalid_files_rejected(tmp_path: Path) -> None:
    """Un fichier qui n'est pas un profil est refusé proprement : ZIP sans
    manifeste, JSON corrompu, nom vide, version future inconnue."""
    manager = _profile_manager(tmp_path)
    not_a_profile = tmp_path / "mods.zip"
    _make_zip(not_a_profile, {"config.json": '{"replacement_rules": []}'})
    with pytest.raises(ProfileError):
        manager.import_profile(not_a_profile)

    corrupt = tmp_path / "corrupt.rcmprofile"
    corrupt.write_text("{ nope", encoding="utf-8")
    with pytest.raises(ProfileError):
        manager.import_profile(corrupt)

    empty = tmp_path / "empty.rcmprofile"
    empty.write_text(json.dumps({"format": 1, "entries": []}), encoding="utf-8")
    with pytest.raises(ProfileError):
        manager.import_profile(empty)

    future = tmp_path / "future.rcmprofile"
    future.write_text(json.dumps({"format": 999, "name": "X", "entries": []}),
                      encoding="utf-8")
    with pytest.raises(ProfileError):
        manager.import_profile(future)


def test_profile_import_persists_after_restart(tmp_path: Path) -> None:
    """Un profil importé reste présent pour une nouvelle instance du
    gestionnaire (persistance sur disque)."""
    directory = tmp_path / "profiles"
    manager = ProfileManager(directory)
    manager.create("Chill", entries=[ProfileEntry(name="sheriff", rel_path="Secondary/Sheriff.json")])
    exported = manager.export_profile("Chill", tmp_path / "Chill.zip")

    ProfileManager(directory).import_profile(exported)  # même nom → copie
    reloaded = ProfileManager(directory)
    names = {p.name for p in reloaded.list_profiles()}
    assert "Chill" in names
    assert any(n != "Chill" and n.startswith("Chill") for n in names)


def test_profiles_view_has_unambiguous_import_button(qapp, tmp_path, monkeypatch) -> None:
    """La page Profils propose « Importer un profil » ; le bouton ambigu
    « Importer dans un profil » (import de mods) a disparu."""
    window, lib = _window(qapp, tmp_path, monkeypatch)
    window.go(("profiles", None))
    qapp.processEvents()
    view = window._profiles_view
    assert not hasattr(view, "_import_into_btn"), "bouton ambigu à supprimer"
    assert "profil" in view._import_btn.text().lower()
    window.close()
