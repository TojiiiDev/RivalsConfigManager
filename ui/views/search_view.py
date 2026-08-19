"""Dedicated search page (v1.3.0).

A real search experience instead of the single top-bar field:

* a **big search bar** at the top with a clear button;
* a **« Récents »** section — the configurations the user recently
  consulted/used (persisted, bounded, most recent first);
* the **same results grid** as the library: results appear in this page as
  soon as a search is run, with the existing category / status filters
  plus the new **favorites** filter (Toutes / Favoris / Non favoris);
* every card feature keeps working: activation button ▶ / ×, right-click,
  navigation, favourite star.

This view is deliberately a *display*: the actual search logic lives in
:mod:`app.search` (``run_search`` / ``SearchState``) and is driven by the
main window — there is no second, independent search implementation.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.categories import display_label, ordered_categories
from app.i18n import t
from app.models import ConfigItem, Node
from app.recents import RecentEntry
from app.search import (
    FAVORITES_EXCLUDED,
    FAVORITES_ONLY,
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    STATUS_MISSING,
    STATUS_SYNC,
)
from ui.icons import close_icon, search_icon
from ui.widgets.grid import CardGrid, CardSpec


class SearchView(QWidget):
    """Dedicated search page: big bar + recents + filters + results."""

    query_changed = Signal(str)                 # big bar text (debounced)
    clear_clicked = Signal()
    config_clicked = Signal(object)             # ConfigItem or Node
    edit_image_requested = Signal(object)       # Node or ConfigItem
    delete_requested = Signal(object)           # Node or ConfigItem
    toggle_activation_requested = Signal(object)  # ConfigItem
    favorite_toggled = Signal(object)           # ConfigItem
    filters_changed = Signal()
    reset_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PageRoot")

        self._title = QLabel("", self)
        self._title.setObjectName("PageTitle")
        self._subtitle = QLabel("", self)
        self._subtitle.setObjectName("PageSubtitle")
        self._subtitle.setWordWrap(True)

        # ---- Big search bar ------------------------------------------- #
        self._big_bar = QLineEdit(self)
        self._big_bar.setPlaceholderText("")
        self._big_bar.setClearButtonEnabled(True)
        self._big_bar.setFixedHeight(44)
        self._big_bar.setMinimumWidth(260)
        self._big_bar.textChanged.connect(self.query_changed)
        # Loupe vectorielle dans la barre (jamais d'emoji).
        self._big_bar.addAction(search_icon(), QLineEdit.LeadingPosition)

        self._clear_btn = QPushButton("", self)
        self._clear_btn.setObjectName("IconButton")
        self._clear_btn.setToolTip("")
        self._clear_btn.setIcon(close_icon())
        self._clear_btn.setIconSize(QSize(16, 16))
        self._clear_btn.clicked.connect(self._on_clear)

        bar_row = QHBoxLayout()
        bar_row.setSpacing(10)
        bar_row.addWidget(self._big_bar, 1)
        bar_row.addWidget(self._clear_btn)

        # ---- Filters (category / status / favorites) ------------------ #
        self._filter_category = QComboBox(self)
        self._filter_category.currentIndexChanged.connect(self._filters_edited)

        self._filter_status = QComboBox(self)
        self._filter_status.currentIndexChanged.connect(self._filters_edited)

        self._filter_favorites = QComboBox(self)
        self._filter_favorites.currentIndexChanged.connect(self._filters_edited)

        self._reset_btn = QPushButton("", self)
        self._reset_btn.setToolTip("")
        self._reset_btn.clicked.connect(self.reset_clicked)
        self._reset_btn.setVisible(False)

        filter_row = QWidget(self)
        filter_layout = QHBoxLayout(filter_row)
        filter_layout.setContentsMargins(0, 0, 0, 0)
        filter_layout.setSpacing(10)
        filter_layout.addWidget(self._filter_category)
        filter_layout.addWidget(self._filter_status)
        filter_layout.addWidget(self._filter_favorites)
        filter_layout.addWidget(self._reset_btn)
        filter_layout.addStretch(1)
        self._filter_row = filter_row

        # ---- Recents -------------------------------------------------- #
        self._recents_label = QLabel("", self)
        self._recents_label.setObjectName("SectionLabel")

        # ---- Results / recents grid ----------------------------------- #
        self._grid = CardGrid(self)
        self._grid.edit_image_requested.connect(self.edit_image_requested)
        self._grid.delete_requested.connect(self.delete_requested)
        self._grid.toggle_activation_requested.connect(self.toggle_activation_requested)
        self._grid.favorite_toggled.connect(self.favorite_toggled)
        self._empty = QLabel("", self)
        self._empty.setObjectName("PageSubtitle")
        self._empty.hide()
        #: Callable key -> bool (favori ?) pour initialiser les étoiles.
        self._favorites_provider: object | None = None
        #: Callable item -> statut intelligent (chip) pour les cartes config.
        self._status_provider: object | None = None
        #: Callable item -> état Fleasion réel (bouton ▶ / × des cartes).
        self._activation_provider: object | None = None

        self.retranslate()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 24, 40, 20)
        layout.setSpacing(14)
        layout.addWidget(self._title)
        layout.addLayout(bar_row)
        layout.addWidget(self._filter_row)
        layout.addWidget(self._recents_label)
        layout.addWidget(self._grid, 1)
        layout.addWidget(self._empty, 1)

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        """Apply the current language to every static text (hot switch)."""
        self._title.setText(t("search.page_title"))
        self._big_bar.setPlaceholderText(t("search.page_placeholder"))
        self._clear_btn.setText(t("search.clear"))
        self._clear_btn.setToolTip(t("search.clear_tooltip"))
        self._recents_label.setText(t("search.recents"))
        self._reset_btn.setText(t("browse.reset"))
        self._reset_btn.setToolTip(t("browse.reset_tooltip"))
        self._empty.setText(t("search.no_recents"))

        current = self._filter_category.currentData()
        self._filter_category.blockSignals(True)
        self._filter_category.clear()
        self._filter_category.addItem(t("browse.filter_all_categories"), None)
        for key in ordered_categories():
            self._filter_category.addItem(display_label(key), key)
        index = self._filter_category.findData(current)
        self._filter_category.setCurrentIndex(index if index >= 0 else 0)
        self._filter_category.blockSignals(False)

        fav = self._filter_favorites.currentData()
        self._filter_favorites.blockSignals(True)
        self._filter_favorites.clear()
        self._filter_favorites.addItem(t("favorites.filter_all"), None)
        self._filter_favorites.addItem(t("favorites.filter_only"), FAVORITES_ONLY)
        self._filter_favorites.addItem(t("favorites.filter_excluded"), FAVORITES_EXCLUDED)
        index = self._filter_favorites.findData(fav)
        self._filter_favorites.setCurrentIndex(index if index >= 0 else 0)
        self._filter_favorites.blockSignals(False)

        self._filter_status.blockSignals(True)
        self._filter_status.setItemText(0, t("browse.filter_all_states"))
        self._filter_status.setItemText(1, t("browse.filter_active"))
        self._filter_status.setItemText(2, t("browse.filter_inactive"))
        self._filter_status.setItemText(3, t("browse.filter_missing"))
        self._filter_status.setItemText(4, t("browse.filter_to_sync"))
        self._filter_status.blockSignals(False)

    # ------------------------------------------------------------------ #
    def query_text(self) -> str:
        return self._big_bar.text()

    def set_favorites_provider(self, provider: object | None) -> None:
        """Fournir le callable key -> bool (favori ?) pour les étoiles."""
        self._favorites_provider = provider

    def set_status_provider(self, provider: object | None) -> None:
        """Callable ConfigItem -> status chip key (or None)."""
        self._status_provider = provider

    def set_activation_provider(self, provider: object | None) -> None:
        """Callable ConfigItem -> Fleasion activation state (bouton ▶ / ×)."""
        self._activation_provider = provider

    def set_query(self, text: str) -> None:
        """Sync the big bar without re-triggering the debounced search."""
        if self._big_bar.text() != text:
            self._big_bar.blockSignals(True)
            self._big_bar.setText(text)
            self._big_bar.blockSignals(False)

    def current_filters(self) -> tuple[str | None, str | None, str | None]:
        """(category, status, favorites) — None means « all »."""
        return (
            self._filter_category.currentData(),
            self._filter_status.currentData(),
            self._filter_favorites.currentData(),
        )

    def set_filters(self, category, status, favorites) -> None:
        self._filter_category.blockSignals(True)
        self._filter_status.blockSignals(True)
        self._filter_favorites.blockSignals(True)
        self._set_combo_value(self._filter_category, category)
        self._set_combo_value(self._filter_status, status)
        self._set_combo_value(self._filter_favorites, favorites)
        self._filter_category.blockSignals(False)
        self._filter_status.blockSignals(False)
        self._filter_favorites.blockSignals(False)
        self._update_reset_visibility()

    def reset_filters(self) -> None:
        self.set_filters(None, None, None)

    # ------------------------------------------------------------------ #
    def show_recents(self, entries: list[RecentEntry]) -> None:
        """« Récents » mode: no query yet — show the recently used configs.

        The recents are rebuilt as config cards (open on click). Missing
        entries (config deleted) are simply not shown.
        """
        self._filter_row.setVisible(False)
        self._recents_label.setVisible(True)
        self._subtitle.setText(t("search.recents_subtitle"))
        specs: list[CardSpec] = []
        for entry in entries:
            specs.append(
                CardSpec(
                    title=entry.name,
                    subtitle=t("search.recent_item"),
                    preview=None,
                    on_click=lambda e=entry: self._open_recent(e),
                    key=entry.key,
                    status=None,
                )
            )
        self._grid.set_cards(specs)
        self._empty.setVisible(not specs)
        self._grid.setVisible(bool(specs))
        if not specs:
            self._empty.setText(t("search.no_recents"))

    def show_results(self, results: list, query: str, library_root: Node) -> None:
        """Search mode: filter bar visible, results in the same page."""
        self._filter_row.setVisible(True)
        self._recents_label.setVisible(False)
        self._title.setText(t("search.results_for", query=query))
        n = len(results)
        self._subtitle.setText(
            t("search.results_found_one", count=n)
            if n == 1
            else t("search.results_found_many", count=n)
        )
        self._empty.setText(t("search.no_results", query=query))
        self._grid.set_reorderable(False)

        specs = []
        for result in results:
            if isinstance(result, Node):
                specs.append(self._folder_spec(result, library_root))
            else:
                specs.append(self._config_spec(result, library_root))
        self._grid.set_cards(specs)
        self._empty.setVisible(not specs)
        self._grid.setVisible(bool(specs))

    # ------------------------------------------------------------------ #
    def _open_recent(self, entry: RecentEntry) -> None:
        """The main window resolves the recent's key into a real config and
        navigates (recents may reference a deleted item: safe no-op)."""
        self.config_clicked.emit(entry)

    def _folder_spec(self, node: Node, library_root: Node) -> CardSpec:
        subtitle = ""
        if library_root is not None:
            try:
                rel = node.path.relative_to(library_root.path)
                subtitle = str(rel.parent) if str(rel.parent) != "." else ""
            except ValueError:
                pass
        count = node.total_items()
        label = t("unit.element_one") if count == 1 else t("unit.element_many")
        if not subtitle:
            subtitle = f"{count} {label}"
        return CardSpec(
            title=node.name,
            subtitle=subtitle,
            preview=node.preview,
            on_click=lambda n=node: self.config_clicked.emit(n),
            edit_target=node,
            delete_target=node,
            key=str(node.path),
        )

    def _config_spec(self, config: ConfigItem, library_root: Node) -> CardSpec:
        subtitle = t("unit.configuration")
        if library_root is not None:
            try:
                rel = config.path.relative_to(library_root.path)
                subtitle = str(rel.parent) if str(rel.parent) != "." else ""
            except ValueError:
                pass
        key = str(config.path)
        provider = self._activation_provider
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
            is_favorite=bool(self._favorites_provider(key))
            if self._favorites_provider is not None else False,
            favorite_target=config if self._favorites_provider is not None else None,
            status=self._status_provider(config)
            if self._status_provider is not None else None,
        )

    # ------------------------------------------------------------------ #
    def _on_clear(self) -> None:
        self.set_query("")
        self.clear_clicked.emit()

    def _filters_edited(self) -> None:
        self._update_reset_visibility()
        self.filters_changed.emit()

    def _update_reset_visibility(self) -> None:
        category, status, favorites = self.current_filters()
        self._reset_btn.setVisible(
            category is not None or status is not None or favorites is not None
        )

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)
