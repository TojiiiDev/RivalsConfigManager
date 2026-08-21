"""Central CardSpec builders — one place that decides what every card shows.

Every card in the application (home categories, sub-folders, weapons,
skins, charms, emotes, FastFlags, texture packs, ...) is built from these
two helpers, so the favourite star — the exact same component everywhere —
can never be forgotten by a view. The star is keyed on the item's **real
path** (``str(item.path)``), never on its displayed name, so two items
sharing a name in different folders stay independent, favourites survive
restarts, and removing a favourite never touches any file.

Views keep their own thin ``_folder_spec`` / ``_config_spec`` wrappers
(they only inject their click signals) — the card logic itself lives here
and nowhere else.
"""

from __future__ import annotations

from app.i18n import t
from app.models import ConfigItem, Node
from ui.widgets.grid import CardSpec


def is_navigation_folder(node: Node, library_root: Node | None = None) -> bool:
    """A folder card is a pure **navigation category** (no favourite star)
    when it only contains other folders, or when it is a top-level category
    of the library (Charms, Emotes, FastFlags, Rivals skins, Textures &
    Skybox, ...).

    A folder that directly contains configurations is a real usable
    container (a weapon holding its skins, a skybox / `Texture packs`
    folder, any sub-folder with configs) and keeps the star. This is the
    semantic distinction between ``Node`` (navigation) and ``ConfigItem``
    (usable) — never based on the element being a physical directory.
    """
    if not node.configs:
        return True
    if library_root is not None and node.path.parent == library_root.path:
        return True
    return False


def folder_spec(
    node: Node,
    on_click: object,
    library_root: Node | None = None,
    favorites_provider: object | None = None,
    is_favorite: bool | None = None,
) -> CardSpec:
    """Card of a folder (category, weapon, sub-folder, folder search result).

    * **Navigation folder** (top-level category or folder containing only
      other folders): NO favourite star — it is not a usable element.
    * **Usable folder** (weapon holding skins, `Texture packs`/skybox
      folder, any folder directly containing configurations): same
      favourite star as every configuration card, keyed on the folder's
      real path — never its displayed name.

    ``is_favorite`` forces the initial state (used by the virtual
    Favorites page, where every shown card is a favourite by construction).
    """
    count = node.total_items()
    label = t("unit.element_one") if count == 1 else t("unit.element_many")
    subtitle = f"{count} {label}"
    if library_root is not None:
        try:
            rel = node.path.relative_to(library_root.path)
            parent = str(rel.parent) if str(rel.parent) != "." else ""
            if parent:
                subtitle = parent
        except ValueError:
            pass
    key = str(node.path)
    if is_favorite is None:
        is_favorite = bool(favorites_provider(key)) if favorites_provider is not None else False
        favorite_target = None if is_navigation_folder(node, library_root) else node
    else:
        favorite_target = node
    return CardSpec(
        title=node.name,
        subtitle=subtitle,
        preview=node.preview,
        on_click=on_click,
        edit_target=node,
        delete_target=node,
        key=key,
        is_favorite=bool(is_favorite),
        favorite_target=favorite_target,
    )


def config_spec(
    config: ConfigItem,
    on_click: object,
    library_root: Node | None = None,
    activation_provider: object | None = None,
    favorites_provider: object | None = None,
    status_provider: object | None = None,
) -> CardSpec:
    """Card of a configuration (single JSON, folder-config, skin, ...).

    Carries the same favourite star, the activation button (▶ / ×) and the
    smart status chip — each initialized from the real source of truth
    (Fleasion state / favorites set / dependency analysis) through the
    provided providers.
    """
    subtitle = t("unit.configuration")
    if config.is_folder:
        n = len(config.files)
        suffix = "s" if n != 1 else ""
        subtitle = t("browse.config_files_subtitle", count=n, s=suffix)
    if library_root is not None:
        try:
            rel = config.path.relative_to(library_root.path)
            subtitle = str(rel.parent) if str(rel.parent) != "." else ""
        except ValueError:
            pass
    key = str(config.path)
    return CardSpec(
        title=config.name,
        subtitle=subtitle,
        preview=config.preview,
        on_click=on_click,
        edit_target=config,
        delete_target=config,
        key=key,
        activation_target=config if activation_provider is not None else None,
        activation_state=activation_provider(config) if activation_provider is not None else None,
        is_favorite=bool(favorites_provider(key)) if favorites_provider is not None else False,
        # Une configuration est TOUJOURS identifiable : la carte porte
        # toujours le même contrôle favori (clé = chemin réel).
        favorite_target=config,
        status=status_provider(config) if status_provider is not None else None,
    )
