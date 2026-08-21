"""Tests for app/categories.py — canonical weapon category order."""

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


from app.categories import (
    CATEGORY_KEYS,
    category_of_path,
    category_rank,
    display_label,
    import_categories,
    ordered_categories,
    sort_configs,
    sort_nodes,
    sort_search_results,
)
from app.models import KIND_FILE, ConfigItem, Node


def test_canonical_order_and_labels() -> None:
    assert CATEGORY_KEYS == ("primary", "secondary", "melee", "utility")
    assert ordered_categories() == ["primary", "secondary", "melee", "utility"]
    assert display_label("primary") == "Primaire"
    assert display_label("secondary") == "Secondaire"
    assert display_label("melee") == "Mêlée"
    assert display_label("utility") == "Utilitaire"


def test_category_rank_english_and_french() -> None:
    assert category_rank("Primary") == 0
    assert category_rank("Secondary") == 1
    assert category_rank("Melee") == 2
    assert category_rank("Utility") == 3
    # French equivalents are recognised too.
    assert category_rank("Primaire") == 0
    assert category_rank("Secondaire") == 1
    assert category_rank("Mêlée") == 2
    assert category_rank("Utilitaire") == 3
    # Case-insensitive, trimmed.
    assert category_rank("PRIMARY") == 0
    assert category_rank("  primary ") == 0
    # Non-category folders have no rank.
    assert category_rank("Charms") is None
    assert category_rank("Texture and skyboxes") is None


def test_category_of_path() -> None:
    assert category_of_path(Path("rivals skins/Primary/Assault Rifle/ak-47.json")) == "primary"
    assert category_of_path(Path("rivals skins/Mêlée/Battle Axe/NordicAxe.json")) == "melee"
    assert category_of_path("rivals skins/Secondary/Hand gun/key handgun.json") == "secondary"
    assert category_of_path(Path("Charms/nemesis charm.json")) is None


def test_sort_nodes_canonical_then_alphabetical() -> None:
    def node(name: str) -> Node:
        return Node(name=name, path=Path(name))

    nodes = sort_nodes(
        [
            node("Utility"),
            node("Charms"),
            node("Melee"),
            node("Primary"),
            node("Secondary"),
            node("emote"),
        ]
    )
    assert [n.name for n in nodes] == [
        "Primary",
        "Secondary",
        "Melee",
        "Utility",
        "Charms",
        "emote",
    ]


def test_sort_nodes_without_categories_stays_alphabetical() -> None:
    def node(name: str) -> Node:
        return Node(name=name, path=Path(name))

    nodes = sort_nodes([node("Texture and skyboxes"), node("Charms"), node("FastFlags")])
    assert [n.name for n in nodes] == ["Charms", "FastFlags", "Texture and skyboxes"]


def test_sort_configs_alphabetical() -> None:
    def item(name: str) -> ConfigItem:
        return ConfigItem(name=name, path=Path(f"{name}.json"), kind=KIND_FILE)

    items = sort_configs([item("Zulu"), item("alpha"), item("Bravo")])
    assert [i.name for i in items] == ["alpha", "Bravo", "Zulu"]


def test_sort_search_results_category_first() -> None:
    def item(name: str, path: str) -> ConfigItem:
        return ConfigItem(name=name, path=Path(path), kind=KIND_FILE)

    results = sort_search_results(
        [
            item("nemesis charm", "Charms/nemesis charm.json"),
            item("ak-47", "rivals skins/Primary/Assault Rifle/ak-47.json"),
            item("key handgun", "rivals skins/Secondary/Hand gun/key handgun.json"),
            item("NordicAxe", "rivals skins/Melee/Battle Axe/NordicAxe.json"),
        ]
    )
    # Canonical category order first, then the rest alphabetically.
    assert [i.name for i in results] == ["ak-47", "key handgun", "NordicAxe", "nemesis charm"]


# ---------------------------------------------------------------------- #
# Import category selector (dynamic, from the real library folders)
# ---------------------------------------------------------------------- #
def test_import_categories_without_library_are_canonical_only() -> None:
    """No library -> the canonical weapon categories, in order."""
    assert import_categories(None) == ["primary", "secondary", "melee", "utility"]
    assert import_categories(Path("/ghost/inexistant")) == [
        "primary",
        "secondary",
        "melee",
        "utility",
    ]


def test_import_categories_include_all_library_folders(tmp_path: Path) -> None:
    """Every top-level folder of the library is a destination, canonical
    categories first, then the rest alphabetically."""
    lib = tmp_path / "Rivals configs"
    for name in ("Textures", "Charms", "Skins", "rivals skins", "Sky"):
        (lib / name).mkdir(parents=True)
    cats = import_categories(lib)
    assert cats[:4] == ["primary", "secondary", "melee", "utility"]
    rest = cats[4:]
    assert set(rest) == {"Textures", "Charms", "Skins", "rivals skins", "Sky"}
    assert rest == sorted(rest, key=str.casefold)


def test_import_categories_include_empty_folder(tmp_path: Path) -> None:
    """An existing but empty category is still proposed as a destination."""
    lib = tmp_path / "Rivals configs"
    (lib / "Skins").mkdir(parents=True)
    (lib / "Charms").mkdir()  # vide
    cats = import_categories(lib)
    assert "Skins" in cats
    assert "Charms" in cats  # vide mais valide


def test_import_categories_new_folder_appears_automatically(tmp_path: Path) -> None:
    """A category created later shows up without any code change."""
    lib = tmp_path / "Rivals configs"
    (lib / "Charms").mkdir(parents=True)
    assert "Charms" in import_categories(lib)
    (lib / "Textures").mkdir()
    assert "Textures" in import_categories(lib)


def test_import_categories_dedupe_canonical_folders(tmp_path: Path) -> None:
    """Top-level folders matching a canonical English name are not listed
    twice: the canonical entry already targets that exact destination."""
    lib = tmp_path / "Rivals configs"
    for name in ("Primary", "Melee", "Secondary", "Utility"):
        (lib / name).mkdir(parents=True)
    (lib / "Charms").mkdir()
    cats = import_categories(lib)
    assert cats == ["primary", "secondary", "melee", "utility", "Charms"]


def test_import_categories_skips_dot_folders(tmp_path: Path) -> None:
    lib = tmp_path / "Rivals configs"
    (lib / ".git").mkdir(parents=True)
    (lib / "Skins").mkdir()
    assert ".git" not in import_categories(lib)
    assert "Skins" in import_categories(lib)
