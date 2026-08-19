"""Home view: the library categories as clickable cards."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.categories import sort_configs, sort_nodes
from app.i18n import t
from app.models import Node
from ui.icons import gear_icon, plus_icon
from ui.widgets.grid import CardGrid, CardSpec

EMPTY_TEXT = "Le dossier de bibliothèque est vide ou introuvable."


class DropZone(QWidget):
    """Discreet drop zone: a small semi-transparent square with a plus
    icon and **no text**. Passing a file over it highlights it slightly;
    releasing the file opens the import popup. Only local file URLs are
    accepted; every other drop is ignored.
    """

    files_dropped = Signal(list)  # list[Path]

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setFixedSize(44, 44)

        icon = QLabel(self)
        icon.setObjectName("DropZoneIcon")
        icon.setPixmap(plus_icon().pixmap(QSize(22, 22)))
        icon.setAlignment(Qt.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(icon)

    # ------------------------------------------------------------------ #
    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if self._has_local_files(event.mimeData()):
            self._set_dragging(True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if self._has_local_files(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._set_dragging(False)
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._set_dragging(False)
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile() and url.toLocalFile()
        ]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    # ------------------------------------------------------------------ #
    def _has_local_files(self, mime) -> bool:
        return any(url.isLocalFile() and url.toLocalFile() for url in mime.urls())

    def _set_dragging(self, active: bool) -> None:
        if self.property("drag") == active:
            return
        self.setProperty("drag", active)
        self.style().unpolish(self)
        self.style().polish(self)


class HomeView(QWidget):
    category_clicked = Signal(object)   # Node
    config_clicked = Signal(object)     # ConfigItem (direct config at root)
    settings_requested = Signal()
    edit_image_requested = Signal(object)  # Node or ConfigItem
    files_dropped = Signal(list)        # list[Path]
    delete_requested = Signal(object)   # Node or ConfigItem
    toggle_activation_requested = Signal(object)  # ConfigItem
    favorite_toggled = Signal(object)  # ConfigItem
    clear_configs_clicked = Signal()
    order_changed = Signal(str, list)   # folder key, ordered card keys

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PageRoot")
        #: Stored drag & drop order (folder key -> ordered card keys),
        #: provided by the main window. Display-only, never the library.
        self.card_order: dict[str, list[str]] = {}
        self._folder_key = ""
        #: Callable item -> Fleasion activation state (source de vérité),
        #: fourni par la fenêtre principale pour initialiser les boutons.
        self._activation_provider: object | None = None
        #: Callable key -> bool (favori ?) pour initialiser les étoiles.
        self._favorites_provider: object | None = None
        #: Callable item -> statut intelligent (chip) pour les cartes config.
        self._status_provider: object | None = None

        self._title = QLabel("RIVALS CONFIG MANAGER", self)
        self._title.setObjectName("AppTitle")
        self._subtitle = QLabel("", self)
        self._subtitle.setObjectName("AppSubtitle")

        self._settings_btn = QPushButton("", self)
        self._settings_btn.setObjectName("IconButton")
        self._settings_btn.setIcon(gear_icon())
        self._settings_btn.setIconSize(QSize(18, 18))
        self._settings_btn.clicked.connect(self.settings_requested)

        # Pas de bouton d'import : la petite zone de drop discrète (en haut
        # à droite) est le seul point d'entrée.
        self._drop_zone = DropZone(self)
        self._drop_zone.files_dropped.connect(self.files_dropped)

        header = QWidget(self)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        header_layout.addWidget(self._title)
        header_layout.addWidget(self._subtitle)

        actions = QWidget(self)
        actions_layout = QHBoxLayout(actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)
        actions_layout.addStretch(1)
        actions_layout.addWidget(self._drop_zone)
        actions_layout.addWidget(self._settings_btn)

        top = QWidget(self)
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(header)
        top_layout.addWidget(actions)

        self._grid = CardGrid(self)
        self._grid.edit_image_requested.connect(self.edit_image_requested)
        self._grid.delete_requested.connect(self.delete_requested)
        self._grid.toggle_activation_requested.connect(self.toggle_activation_requested)
        self._grid.favorite_toggled.connect(self.favorite_toggled)
        self._grid.order_changed.connect(self._on_order_changed)
        self._empty = QLabel("", self)
        self._empty.setObjectName("PageSubtitle")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.hide()

        # ---- Bottom-right: « Clear Configs » (discreet, only touches the
        # Fleasion configs folder — files go to the Windows Recycle Bin) -- #
        self._clear_configs_btn = QPushButton("", self)
        self._clear_configs_btn.setObjectName("ClearButton")
        self._clear_configs_btn.setCursor(Qt.PointingHandCursor)
        self._clear_configs_btn.setToolTip("")
        self._clear_configs_btn.clicked.connect(self.clear_configs_clicked)

        bottom = QWidget(self)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.addStretch(1)
        bottom_layout.addWidget(self._clear_configs_btn)

        self.retranslate()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 28, 40, 20)
        layout.setSpacing(16)
        layout.addWidget(top)
        layout.addWidget(self._grid, 1)
        layout.addWidget(self._empty, 1)
        layout.addWidget(bottom)

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        """Apply the current language to every static text (hot switch)."""
        self._subtitle.setText(t("home.subtitle"))
        self._settings_btn.setText(t("settings.button"))
        self._clear_configs_btn.setText(t("home.clear_configs"))
        self._clear_configs_btn.setToolTip(t("home.clear_configs_tooltip"))
        self._empty.setText(t("home.empty"))

    # ------------------------------------------------------------------ #
    def set_activation_provider(self, provider: object | None) -> None:
        """Fournir le callable donnant l'état réel Fleasion d'une carte
        (utilisé pour initialiser le bouton d'activation des configs)."""
        self._activation_provider = provider

    def set_favorites_provider(self, provider: object | None) -> None:
        """Fournir le callable key -> bool (favori ?) pour les étoiles."""
        self._favorites_provider = provider

    def set_status_provider(self, provider: object | None) -> None:
        """Callable ConfigItem -> status chip key (or None)."""
        self._status_provider = provider

    # ------------------------------------------------------------------ #
    def set_library(self, root: Node | None) -> None:
        specs: list[CardSpec] = []
        if root is not None:
            self._folder_key = str(root.path)
            # Ordre canonique des catégories (Primaire → Secondaire → Mêlée
            # → Utilitaire), puis le reste par ordre alphabétique.
            for sub in sort_nodes(root.subdirs):
                count = sub.total_items()
                label = t("unit.element_one") if count == 1 else t("unit.element_many")
                specs.append(
                    CardSpec(
                        title=sub.name,
                        subtitle=f"{count} {label}",
                        preview=sub.preview,
                        on_click=lambda n=sub: self.category_clicked.emit(n),
                        edit_target=sub,
                        delete_target=sub,
                        key=str(sub.path),
                    )
                )
            for config in sort_configs(root.configs):
                key = str(config.path)
                specs.append(
                    CardSpec(
                        title=config.name,
                        subtitle=t("unit.configuration"),
                        preview=config.preview,
                        on_click=lambda c=config: self.config_clicked.emit(c),
                        edit_target=config,
                        delete_target=config,
                        key=key,
                        activation_target=config,
                        activation_state=self._card_state(config),
                        is_favorite=bool(self._favorites_provider(key))
                        if self._favorites_provider is not None else False,
                        favorite_target=config if self._favorites_provider is not None else None,
                        status=self._status_provider(config)
                        if self._status_provider is not None else None,
                    )
                )
        self._grid.set_cards(self._apply_stored_order(specs))
        self._empty.setVisible(not specs)
        self._grid.setVisible(bool(specs))

    def _apply_stored_order(self, specs: list[CardSpec]) -> list[CardSpec]:
        """Réordonner les cartes selon l'ordre glisser-déposer stocké (les
        clés inconnues — nouveaux éléments — gardent leur position relative
        canonique, en fin de liste)."""
        stored = self.card_order.get(self._folder_key, [])
        if not stored:
            return specs
        rank = {key: i for i, key in enumerate(stored)}
        return sorted(specs, key=lambda s: (rank.get(s.key, len(stored)), 0))

    def _on_order_changed(self, keys: list[str]) -> None:
        if self._folder_key:
            self.order_changed.emit(self._folder_key, list(keys))

    def _card_state(self, config: object) -> str | None:
        if self._activation_provider is None:
            return None
        return self._activation_provider(config)
