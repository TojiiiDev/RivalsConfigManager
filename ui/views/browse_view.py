"""Browse view: sub-folders and configurations of a library node, plus the
search results page with its discreet filter bar (category + status)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.categories import (
    display_label,
    ordered_categories,
    sort_configs,
    sort_nodes,
)
from app.i18n import t
from app.models import ConfigItem, Node
from app.search import (
    STATUS_ACTIVE,
    STATUS_INACTIVE,
    STATUS_MISSING,
    STATUS_SYNC,
)
from ui.card_specs import config_spec, folder_spec
from ui.widgets.grid import CardGrid, CardSpec

EMPTY_FOLDER_TEXT = "Aucun élément dans ce dossier."


class BrowseView(QWidget):
    folder_clicked = Signal(object)   # Node
    config_clicked = Signal(object)   # ConfigItem
    edit_image_requested = Signal(object)  # Node or ConfigItem
    delete_requested = Signal(object)  # Node or ConfigItem
    toggle_activation_requested = Signal(object)  # ConfigItem
    favorite_toggled = Signal(object)  # ConfigItem
    filters_changed = Signal()
    reset_clicked = Signal()
    order_changed = Signal(str, list)   # folder key, ordered card keys

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PageRoot")
        #: Stored drag & drop order (folder key -> ordered card keys).
        self.card_order: dict[str, list[str]] = {}
        self._folder_key = ""
        #: Callable item -> Fleasion activation state (source de vérité),
        #: fourni par la fenêtre principale pour initialiser les boutons.
        self._activation_provider: object | None = None
        #: Callable key -> bool (favori ?) pour initialiser les étoiles.
        self._favorites_provider: object | None = None
        #: Callable item -> statut intelligent (chip) pour les cartes config.
        self._status_provider: object | None = None

        self._title = QLabel("", self)
        self._title.setObjectName("PageTitle")
        self._subtitle = QLabel("", self)
        self._subtitle.setObjectName("PageSubtitle")

        header = QVBoxLayout()
        header.setSpacing(4)
        header.addWidget(self._title)
        header.addWidget(self._subtitle)

        # ---- Discreet filter bar (visible only during a search) ---------- #
        self._filter_category = QComboBox(self)
        self._filter_category.addItem("", None)
        for key in ordered_categories():
            self._filter_category.addItem(display_label(key), key)
        self._filter_category.currentIndexChanged.connect(self._filters_edited)

        self._filter_status = QComboBox(self)
        self._filter_status.addItem("", None)
        self._filter_status.addItem("", STATUS_ACTIVE)
        self._filter_status.addItem("", STATUS_INACTIVE)
        self._filter_status.addItem("", STATUS_MISSING)
        self._filter_status.addItem("", STATUS_SYNC)
        self._filter_status.currentIndexChanged.connect(self._filters_edited)

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
        filter_layout.addWidget(self._reset_btn)
        filter_layout.addStretch(1)
        self._filter_row = filter_row
        self._filter_row.setVisible(False)

        self._grid = CardGrid(self)
        self._grid.edit_image_requested.connect(self.edit_image_requested)
        self._grid.delete_requested.connect(self.delete_requested)
        self._grid.toggle_activation_requested.connect(self.toggle_activation_requested)
        self._grid.favorite_toggled.connect(self.favorite_toggled)
        self._grid.order_changed.connect(self._on_order_changed)
        self._empty = QLabel("", self)
        self._empty.setObjectName("PageSubtitle")
        self._empty.hide()

        self.retranslate()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 24, 40, 20)
        layout.setSpacing(14)
        layout.addLayout(header)
        layout.addWidget(self._filter_row)
        layout.addWidget(self._grid, 1)
        layout.addWidget(self._empty, 1)

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        """Apply the current language to the filter bar and empty state
        (cards are rebuilt by set_node / show_search_results)."""
        current = self._filter_category.currentData()
        self._filter_category.blockSignals(True)
        self._filter_category.clear()
        self._filter_category.addItem(t("browse.filter_all_categories"), None)
        for key in ordered_categories():
            self._filter_category.addItem(display_label(key), key)
        index = self._filter_category.findData(current)
        self._filter_category.setCurrentIndex(index if index >= 0 else 0)
        self._filter_category.blockSignals(False)
        self._filter_status.blockSignals(True)
        self._filter_status.setItemText(0, t("browse.filter_all_states"))
        self._filter_status.setItemText(1, t("browse.filter_active"))
        self._filter_status.setItemText(2, t("browse.filter_inactive"))
        self._filter_status.setItemText(3, t("browse.filter_missing"))
        self._filter_status.setItemText(4, t("browse.filter_to_sync"))
        self._filter_status.blockSignals(False)
        self._reset_btn.setText(t("browse.reset"))
        self._reset_btn.setToolTip(t("browse.reset_tooltip"))
        self._empty.setText(t("browse.empty_folder"))

    # ------------------------------------------------------------------ #
    def set_activation_provider(self, provider: object | None) -> None:
        """Fournir le callable donnant l'état réel Fleasion d'une carte."""
        self._activation_provider = provider

    def set_favorites_provider(self, provider: object | None) -> None:
        """Fournir le callable key -> bool (favori ?) pour les étoiles."""
        self._favorites_provider = provider

    def set_status_provider(self, provider: object | None) -> None:
        """Callable ConfigItem -> status chip key (or None)."""
        self._status_provider = provider

    # ------------------------------------------------------------------ #
    def set_node(self, node: Node) -> None:
        """Normal browsing: no filter bar, plain folder content."""
        self._filter_row.setVisible(False)
        self._empty.setText(t("browse.empty_folder"))
        self._title.setText(node.name)
        n_sub = len(node.subdirs)
        n_cfg = len(node.configs)
        bits = []
        if n_sub:
            bits.append(
                f"{n_sub} "
                + (t("unit.folder_one") if n_sub == 1 else t("unit.folder_many"))
            )
        if n_cfg:
            bits.append(
                f"{n_cfg} "
                + (t("unit.configuration") if n_cfg == 1 else t("unit.configuration_many"))
            )
        self._subtitle.setText(" · ".join(bits))
        self._folder_key = str(node.path)
        self._grid.set_reorderable(True)

        specs: list[CardSpec] = []
        # Ordre canonique des catégories, puis le reste par ordre alphabétique.
        for sub in sort_nodes(node.subdirs):
            count = sub.total_items()
            label = t("unit.element_one") if count == 1 else t("unit.element_many")
            specs.append(self._folder_spec(sub))
        for config in sort_configs(node.configs):
            specs.append(self._config_spec(config))
        self._grid.set_cards(self._apply_stored_order(specs))
        self._empty.setVisible(not specs)
        self._grid.setVisible(bool(specs))

    # ------------------------------------------------------------------ #
    def show_search_results(self, results: list[ConfigItem], query: str, library_root: Node) -> None:
        """Search mode: filter bar visible, count in the subtitle, clean
        empty state when nothing matches."""
        self._filter_row.setVisible(True)
        self._title.setText(t("search.results_for", query=query))
        n = len(results)
        self._subtitle.setText(
            t("search.results_found_one", count=n)
            if n == 1
            else t("search.results_found_many", count=n)
        )
        self._empty.setText(t("search.no_results", query=query))
        self._folder_key = ""  # pas de réorganisation persistée en recherche
        self._grid.set_reorderable(False)

        # Les résultats peuvent être des dossiers (recherche hiérarchique) :
        # un dossier correspondant exactement à la requête s'affiche avant
        # ses enfants et ouvre sa page au clic.
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
    # Filters
    # ------------------------------------------------------------------ #
    def current_filters(self) -> tuple[str | None, str | None]:
        """(category, status) currently selected — None means « all »."""
        return (self._filter_category.currentData(), self._filter_status.currentData())

    def set_filters(self, category: str | None, status: str | None) -> None:
        """Restore filters without retriggering the change signal."""
        self._filter_category.blockSignals(True)
        self._filter_status.blockSignals(True)
        self._set_combo_value(self._filter_category, category)
        self._set_combo_value(self._filter_status, status)
        self._filter_category.blockSignals(False)
        self._filter_status.blockSignals(False)
        self._update_reset_visibility()

    def reset_filters(self) -> None:
        self.set_filters(None, None)

    # ------------------------------------------------------------------ #
    def _filters_edited(self) -> None:
        self._update_reset_visibility()
        self.filters_changed.emit()

    def _update_reset_visibility(self) -> None:
        category, status = self.current_filters()
        self._reset_btn.setVisible(category is not None or status is not None)

    @staticmethod
    def _set_combo_value(combo: QComboBox, value: object) -> None:
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    # ------------------------------------------------------------------ #
    def _folder_spec(self, node: Node, library_root: Node | None = None) -> CardSpec:
        """Card of a folder (category, weapon, sub-folder or hierarchical
        search result): the subtitle shows its real place in the tree;
        clicking opens the folder's page. Built by the central builder
        (ui.card_specs) so it carries the **same favourite star as every
        other card** — same position, same interaction, same persistence
        (v1.3.4/1.3.5, jamais dupliqué)."""
        return folder_spec(
            node,
            on_click=lambda n=node: self.folder_clicked.emit(n),
            library_root=library_root,
            favorites_provider=self._favorites_provider,
        )

    # ------------------------------------------------------------------ #
    def _config_spec(self, config: ConfigItem, library_root: Node | None = None) -> CardSpec:
        """Card of a configuration — built by the central builder so the
        favourite star, the activation button and the status chip are the
        exact same components as everywhere else."""
        return config_spec(
            config,
            on_click=lambda c=config: self.config_clicked.emit(c),
            library_root=library_root,
            activation_provider=self._activation_provider,
            favorites_provider=self._favorites_provider,
            status_provider=self._status_provider,
        )

    # ------------------------------------------------------------------ #
    def _apply_stored_order(self, specs: list[CardSpec]) -> list[CardSpec]:
        """Réordonner les cartes selon l'ordre glisser-déposer stocké."""
        stored = self.card_order.get(self._folder_key, [])
        if not stored:
            return specs
        rank = {key: i for i, key in enumerate(stored)}
        return sorted(specs, key=lambda s: (rank.get(s.key, len(stored)), 0))

    def _on_order_changed(self, keys: list[str]) -> None:
        if self._folder_key:
            self.order_changed.emit(self._folder_key, list(keys))
