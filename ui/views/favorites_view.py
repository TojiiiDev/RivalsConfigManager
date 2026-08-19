"""Favorites view (v1.3.2): a **virtual folder** listing the favourite
configurations.

The files stay in their original category — this page is a pure shortcut:
it gathers the configurations whose key is in the favourites set and shows
them as normal cards (same Card / image / activation / star system as the
library). Removing the favourite removes the card from this page; the file
is never touched.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from app.categories import sort_configs
from app.i18n import t
from app.models import ConfigItem, Node
from ui.widgets.grid import CardGrid, CardSpec


class FavoritesView(QWidget):
    config_clicked = Signal(object)             # ConfigItem
    edit_image_requested = Signal(object)       # ConfigItem
    delete_requested = Signal(object)           # ConfigItem
    toggle_activation_requested = Signal(object)  # ConfigItem
    favorite_toggled = Signal(object)           # ConfigItem

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PageRoot")
        #: Callable item -> Fleasion activation state (bouton ▶ / ×).
        self._activation_provider: object | None = None
        #: Callable key -> bool (favori ?) pour les étoiles.
        self._favorites_provider: object | None = None
        #: Callable item -> statut intelligent (chip).
        self._status_provider: object | None = None

        self._title = QLabel("", self)
        self._title.setObjectName("PageTitle")
        self._subtitle = QLabel("", self)
        self._subtitle.setObjectName("PageSubtitle")
        self._subtitle.setWordWrap(True)

        self._grid = CardGrid(self)
        self._grid.edit_image_requested.connect(self.edit_image_requested)
        self._grid.delete_requested.connect(self.delete_requested)
        self._grid.toggle_activation_requested.connect(self.toggle_activation_requested)
        self._grid.favorite_toggled.connect(self.favorite_toggled)
        self._empty = QLabel("", self)
        self._empty.setObjectName("PageSubtitle")
        self._empty.setWordWrap(True)
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.hide()

        self.retranslate()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 24, 40, 20)
        layout.setSpacing(14)
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)
        layout.addWidget(self._grid, 1)
        layout.addWidget(self._empty, 1)

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        self._title.setText(t("favorites.title"))
        self._subtitle.setText(t("favorites.subtitle"))
        self._empty.setText(t("favorites.empty"))

    # ------------------------------------------------------------------ #
    def set_activation_provider(self, provider: object | None) -> None:
        self._activation_provider = provider

    def set_favorites_provider(self, provider: object | None) -> None:
        self._favorites_provider = provider

    def set_status_provider(self, provider: object | None) -> None:
        self._status_provider = provider

    # ------------------------------------------------------------------ #
    def set_favorites(self, configs: list[ConfigItem], library_root: Node | None) -> None:
        """Show the favourite configurations as normal cards (virtual view:
        the files stay in their original category)."""
        n = len(configs)
        self._subtitle.setText(
            t("favorites.count_one") if n == 1 else t("favorites.count_many", count=n)
        )
        specs = []
        for config in sort_configs(configs):
            specs.append(self._config_spec(config, library_root))
        self._grid.set_reorderable(False)
        self._grid.set_cards(specs)
        self._empty.setVisible(not specs)
        self._grid.setVisible(bool(specs))

    # ------------------------------------------------------------------ #
    def _config_spec(self, config: ConfigItem, library_root: Node | None) -> CardSpec:
        subtitle = t("unit.configuration")
        if library_root is not None:
            try:
                rel = config.path.relative_to(library_root.path)
                subtitle = str(rel.parent) if str(rel.parent) != "." else ""
            except ValueError:
                pass
        provider = self._activation_provider
        fav_provider = self._favorites_provider
        status_provider = self._status_provider
        key = str(config.path)
        return CardSpec(
            title=config.name,
            subtitle=subtitle,
            preview=config.preview,
            on_click=lambda c=config: self.config_clicked.emit(c),
            edit_target=config,
            delete_target=config,
            key=key,
            activation_target=config if provider is not None else None,
            activation_state=provider(config) if provider is not None else None,
            is_favorite=bool(fav_provider(key)) if fav_provider is not None else False,
            favorite_target=config if fav_provider is not None else None,
            status=status_provider(config) if status_provider is not None else None,
        )
