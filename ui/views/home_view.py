"""Home view: the library categories as clickable cards + the drop zone.

The drop zone is the FIRST thing a new user must understand: « I can drag my
files here to add them ». It is therefore a large, labeled zone (icon +
title + subtitle) with clear normal / hover / drag-over states, a light
animation on drag-over, and a click-to-browse action that reuses the exact
same import flow as a drop (never a second import system).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import QColor, QCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.categories import sort_configs, sort_nodes
from app.i18n import t
from app.models import Node
from ui.card_specs import config_spec, folder_spec
from ui.icons import plus_icon
from ui.theme import theme_color
from ui.widgets.grid import CardGrid, CardSpec

EMPTY_TEXT = "Le dossier de bibliothèque est vide ou introuvable."


class DropZone(QWidget):
    """Large, self-explanatory drop zone (UI/UX phase).

    * normal state: dashed accent border + subtle tint, icon + title +
      subtitle (« Glissez-déposez vos fichiers ici pour les ajouter » /
      « Vous pouvez également cliquer pour parcourir vos fichiers »);
    * hover state: stronger tint and border;
    * drag-over state: accent highlight with a light glow animation and a
      clear « this zone accepts the file » feedback;
    * click: opens the file browser (same import flow as a drop).

    Only local file URLs are accepted; every other drop is ignored. The
    whole visual is driven by the active theme (inline stylesheet) so it
    follows theme switches like the rest of the application.
    """

    files_dropped = Signal(list)   # list[Path]
    browse_clicked = Signal()      # click → file browser

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMinimumHeight(86)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._hover = False
        self._dragging = False
        self._glow = 0.0
        self._press_pos: QPoint | None = None

        # ---- Icon + title + subtitle ---------------------------------- #
        self._icon = QLabel(self)
        self._icon.setObjectName("DropZoneIcon")
        self._icon.setPixmap(plus_icon().pixmap(QSize(26, 26)))
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._title = QLabel("", self)
        self._title.setObjectName("DropZoneTitle")
        self._title.setAlignment(Qt.AlignCenter)
        self._title.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._subtitle = QLabel("", self)
        self._subtitle.setObjectName("DropZoneSubtitle")
        self._subtitle.setAlignment(Qt.AlignCenter)
        self._subtitle.setAttribute(Qt.WA_TransparentForMouseEvents)

        texts = QVBoxLayout()
        texts.setContentsMargins(0, 0, 0, 0)
        texts.setSpacing(2)
        texts.addWidget(self._title)
        texts.addWidget(self._subtitle)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 14, 24, 14)
        layout.setSpacing(18)
        layout.addWidget(self._icon, 0, Qt.AlignVCenter)
        layout.addLayout(texts, 1)

        # ---- Light glow animation (drag-over / hover) ------------------ #
        self._anim = QPropertyAnimation(self, b"glow", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

        self.retranslate()
        self._apply_visual()

    # ------------------------------------------------------------------ #
    # Visual states (driven by the active theme)
    # ------------------------------------------------------------------ #
    def _get_glow(self) -> float:
        return self._glow

    def _set_glow(self, value: float) -> None:
        self._glow = max(0.0, min(1.0, float(value)))
        self._apply_visual()

    glow = Property(float, _get_glow, _set_glow)

    def _apply_visual(self) -> None:
        """Rebuild the inline stylesheet from the active theme colors.

        Normal: subtle dashed accent border. Hover: stronger. Drag-over:
        full accent highlight (the glow animation interpolates it).
        """
        accent = QColor(theme_color("accent"))
        text = QColor(theme_color("text"))
        dim = QColor(theme_color("text_dim"))
        glow = 1.0 if self._dragging else (0.35 if self._hover else 0.0)
        border_alpha = int(80 + 175 * glow)
        bg_alpha = int(10 + 80 * glow)
        border_style = "solid" if self._dragging else "dashed"
        self.setStyleSheet(
            f"QWidget#DropZone {{"
            f" background-color: rgba({accent.red()}, {accent.green()}, {accent.blue()}, {bg_alpha});"
            f" border: 2px {border_style} rgba({accent.red()}, {accent.green()}, {accent.blue()}, {border_alpha});"
            f" border-radius: 16px; }}"
            f"QWidget#DropZone QLabel {{ border: none; background: transparent; }}"
            f"QLabel#DropZoneTitle {{ color: {text.name()}; font-size: 11.5pt; font-weight: 600; }}"
            f"QLabel#DropZoneSubtitle {{ color: {dim.name()}; font-size: 9.5pt; }}"
        )

    def retranslate(self) -> None:
        """Apply the current language to the drop zone texts (hot switch)."""
        self._title.setText(t("home.drop_zone_title"))
        self._subtitle.setText(t("home.drop_zone_subtitle"))

    # ------------------------------------------------------------------ #
    # Hover
    # ------------------------------------------------------------------ #
    def enterEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._hover = True
        self._apply_visual()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._hover = False
        self._apply_visual()
        super().leaveEvent(event)

    # ------------------------------------------------------------------ #
    # Click → browse files
    # ------------------------------------------------------------------ #
    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        was_pressed = self._press_pos is not None
        self._press_pos = None
        if (
            event.button() == Qt.LeftButton
            and was_pressed
            and self.rect().contains(event.position().toPoint())
        ):
            self.browse_clicked.emit()
        super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------ #
    # Drag & drop (only local files — same import flow as before)
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

    def _has_local_files(self, mime) -> bool:
        return any(url.isLocalFile() and url.toLocalFile() for url in mime.urls())

    def _set_dragging(self, active: bool) -> None:
        """Smoothly animate the highlight in (drag-over) or out (leave)."""
        if self._dragging == active:
            return
        self._dragging = active
        self.setProperty("drag", active)
        self._anim.stop()
        self._anim.setStartValue(self._glow)
        self._anim.setEndValue(1.0 if active else 0.0)
        self._anim.start()
        self._apply_visual()


class HomeView(QWidget):
    category_clicked = Signal(object)   # Node
    config_clicked = Signal(object)     # ConfigItem (direct config at root)
    edit_image_requested = Signal(object)  # Node or ConfigItem
    files_dropped = Signal(list)        # list[Path]
    browse_clicked = Signal()           # clic sur la zone de dépôt
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

        header = QWidget(self)
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        header_layout.addWidget(self._title)
        header_layout.addWidget(self._subtitle)

        # ---- La zone de dépôt : grande, explicite, pleine largeur. Le
        # bouton Paramètres secondaire (doublon avec celui de la barre du
        # haut) a été supprimé ; l'espace sert à la zone de dépôt.
        self._drop_zone = DropZone(self)
        self._drop_zone.files_dropped.connect(self.files_dropped)
        self._drop_zone.browse_clicked.connect(self.browse_clicked)

        top = QWidget(self)
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(12)
        top_layout.addWidget(header)
        top_layout.addWidget(self._drop_zone)

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
        self._drop_zone.retranslate()
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
            # → Utilitaire), puis le reste par ordre alphabétique. Toutes les
            # cartes sont construites par les constructeurs centraux
            # (ui.card_specs) : la même étoile favori, le même emplacement,
            # la même interaction et la même persistance pour chaque carte
            # — aucune vue ne peut oublier le contrôle favori (v1.3.4/1.3.5).
            for sub in sort_nodes(root.subdirs):
                specs.append(
                    folder_spec(
                        sub,
                        on_click=lambda n=sub: self.category_clicked.emit(n),
                        library_root=root,
                        favorites_provider=self._favorites_provider,
                    )
                )
            for config in sort_configs(root.configs):
                specs.append(
                    config_spec(
                        config,
                        on_click=lambda c=config: self.config_clicked.emit(c),
                        activation_provider=self._activation_provider,
                        favorites_provider=self._favorites_provider,
                        status_provider=self._status_provider,
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
