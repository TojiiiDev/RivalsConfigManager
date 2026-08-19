"""Clickable card widget used for categories, folders and configs.

The hover "lift" animation must never change the card's logical position in
the grid. The card is therefore NOT managed by the QGridLayout: it lives
inside a :class:`ui.widgets.grid.CardCell` which is the layout item, and the
card is positioned manually inside its cell (rest position ``(0, TOP)``).
The animation moves the card by a few pixels *within its own cell*, so the
grid layout is never disturbed and the card always comes back exactly to its
cell.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import (
    Property,
    QEasingCurve,
    QEvent,
    QMimeData,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QCursor,
    QDrag,
    QFontMetrics,
    QPainter,
    QPalette,
    QPixmap,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

#: Custom MIME type used for internal card drag & drop. Deliberately NOT
#: a file URL mime: the window-level drop handler (file import) ignores it,
#: so reordering a card can never trigger the import popup.
CARD_DRAG_MIME = "application/x-rcm-card-order"

from app.i18n import t
from ui.icons import close_icon, play_icon, star_icon
from ui.theme import ACCENT, DANGER, SUCCESS, WARNING, theme_color

from .preview import PreviewLabel

#: Side (px) of the small favourite star on configuration cards.
FAV_SIZE = 26

#: Status chip semantic keys (v1.3.0 smart card status).
STATUS_READY = "ready"
STATUS_INCOMPLETE = "incomplete"
STATUS_ERROR = "error"
STATUS_ACTIVE = "active"

#: Status chip -> (i18n key, color name). "active" wins over "ready": an
#: active configuration is shown as active, never merely as ready.
_STATUS_STYLES = {
    STATUS_READY: ("card.status_ready", SUCCESS),
    STATUS_INCOMPLETE: ("card.status_incomplete", WARNING),
    STATUS_ERROR: ("card.status_error", DANGER),
    STATUS_ACTIVE: ("card.status_active", ACCENT),
}

#: Vertical lift (in pixels) applied when the mouse hovers a card.
LIFT_PIXELS = 5

#: Fixed height (px) of the preview zone at the top of a card.
PREVIEW_HEIGHT = 150

#: Maximum number of lines shown for a card title before eliding with "…".
TITLE_MAX_LINES = 2

#: Side (px) of the small square activation button on configuration cards.
TOGGLE_SIZE = 32

#: QSS of the square activation button — accent (inactive) / danger (active).
#: Built from the active theme's colors (v1.3.0 themes).
def _toggle_qss(base: str, hover: str, pressed: str, disabled: str) -> str:
    return (
        "QPushButton { background-color: " + base + "; border: none;"
        " border-radius: 8px; }"
        "QPushButton:hover { background-color: " + hover + "; }"
        "QPushButton:pressed { background-color: " + pressed + "; }"
        "QPushButton:disabled { background-color: " + disabled + "; }"
    )


class ElidedLabel(QLabel):
    """A label that wraps up to ``max_lines`` lines and elides the rest.

    The text is elided with "…" when it does not fit, so long names stay
    readable without blowing up the card. Rendering stays native (QSS colors
    and fonts apply normally); only the displayed text is adjusted.
    """

    def __init__(self, text: str = "", parent=None, max_lines: int = TITLE_MAX_LINES) -> None:
        super().__init__(parent)
        self._max_lines = max(1, max_lines)
        self._raw_text = text
        self._shown_text = text
        self.setWordWrap(True)
        # Horizontal: Expanding so the label always claims the whole width
        # that the row leaves for it. A wrapping QLabel's ``sizeHint`` is
        # only as wide as its widest word, so with a mere "Preferred"
        # policy the layout would shrink the title to a few characters.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._update_min_height()
        self._apply_elide()

    # ------------------------------------------------------------------ #
    def setText(self, text: str) -> None:
        self._raw_text = text
        self._apply_elide()

    def text(self) -> str:
        """Return the full (un-elided) text."""
        return self._raw_text

    def changeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().changeEvent(event)
        if event.type() == QEvent.FontChange:
            self._update_min_height()
            self._apply_elide()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._apply_elide()

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        """Draw the text centered, wrapping up to max_lines with an ellipsis."""
        if not self._raw_text:
            super().paintEvent(event)
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        fm = QFontMetrics(self.font())
        painter.setFont(self.font())
        painter.setPen(self.palette().color(QPalette.WindowText))

        width = self.width()
        lines = self._wrap(fm, self._raw_text, width)
        if len(lines) > self._max_lines:
            shown = lines[: self._max_lines]
            last = " ".join(lines[self._max_lines - 1 :])
            shown[-1] = fm.elidedText(last, Qt.ElideRight, width)
        else:
            shown = lines

        line_height = fm.height()
        block_height = len(shown) * line_height
        y = max(0, (self.height() - block_height) // 2)
        for line in shown:
            x = max(0, (width - fm.horizontalAdvance(line)) // 2)
            painter.drawText(x, y + fm.ascent(), line)
            y += line_height
        painter.end()

    # ------------------------------------------------------------------ #
    def _update_min_height(self) -> None:
        fm = QFontMetrics(self.font())
        self.setMinimumHeight(fm.height() * self._max_lines)

    @staticmethod
    def _wrap(fm: QFontMetrics, text: str, width: int) -> list[str]:
        lines: list[str] = []
        current = ""
        for word in text.split():
            candidate = (current + " " + word).strip()
            if not current or fm.horizontalAdvance(candidate) <= width:
                current = candidate
            else:
                lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines or [""]

    def _apply_elide(self) -> None:
        if not self._raw_text:
            return
        width = max(self.width(), 60)
        fm = QFontMetrics(self.font())
        lines = self._wrap(fm, self._raw_text, width)
        if len(lines) > self._max_lines:
            # Merge everything after the kept lines into the last one so
            # the ellipsis is always visible when text is truncated.
            shown = lines[: self._max_lines]
            last = " ".join(lines[self._max_lines - 1 :])
            shown[-1] = fm.elidedText(last, Qt.ElideRight, width)
            new_text = "\n".join(shown)
        else:
            new_text = "\n".join(lines)
        if new_text != self._shown_text:
            self._shown_text = new_text
            blocked = self.blockSignals(True)
            super().setText(new_text)
            self.blockSignals(blocked)


class Card(QFrame):
    """A rounded card with a preview, a title and a subtitle.

    Hovering lifts the card slightly (smooth animation) and highlights its
    border. Clicking emits :attr:`clicked`. Right-clicking opens a small
    context menu ("Modifier l'image") that emits :attr:`edit_image_requested`.
    """

    clicked = Signal()
    edit_image_requested = Signal()
    delete_requested = Signal()
    toggle_activation_requested = Signal()
    favorite_toggled = Signal()

    _lift = 0.0  # animated 0 -> 1

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        preview: Path | None = None,
        parent=None,
        key: str = "",
        activation_state: str | None = None,
        is_favorite: bool = False,
        status: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setMinimumSize(180, 210)
        #: Stable identity used for drag & drop reordering (a path or name).
        self.drag_key = key or title
        self._press_pos: QPoint | None = None
        self._dragging = False

        self._has_image = preview is not None

        # ---- Preview zone: fixed height, image/placeholder contained ------ #
        # The preview container is a dedicated zone with a fixed height. It
        # never contains the name: the two zones (preview / name) are fully
        # independent, so the text can never be hidden behind the image.
        self._preview_zone = QFrame(self)
        self._preview_zone.setObjectName("PreviewZone")
        self._preview_zone.setFixedHeight(PREVIEW_HEIGHT)
        zone_layout = QVBoxLayout(self._preview_zone)
        zone_layout.setContentsMargins(0, 0, 0, 0)
        self._preview = PreviewLabel(None, self._preview_zone)  # fit mode
        self._preview.set_path(preview, title)
        zone_layout.addWidget(self._preview)

        # ---- Smart status chip (v1.3.0): overlaid at the top-LEFT of the
        # preview zone. It is absolutely positioned inside the card and
        # NEVER competes with the title row: the name keeps its full width.
        self._status_label = QLabel("", self)
        self._status_label.setStyleSheet(
            "border: none; background: transparent; font-size: 8pt;"
            " font-weight: 700; padding: 2px 4px;"
        )
        self._status_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._status_label.hide()

        # ---- Favourite star (v1.3.0): top-RIGHT of the preview zone,
        # absolutely positioned — the name row layout is untouched.
        self._fav_btn = QPushButton(self)
        self._fav_btn.setObjectName("CardFavButton")
        self._fav_btn.setFixedSize(FAV_SIZE, FAV_SIZE)
        self._fav_btn.setIconSize(QSize(16, 16))
        self._fav_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._fav_btn.setContextMenuPolicy(Qt.DefaultContextMenu)
        self._fav_btn.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            " border-radius: 8px; }"
            "QPushButton:hover { background-color: rgba(255, 255, 255, 0.12); }"
        )
        self._fav_btn.clicked.connect(self._on_favorite_clicked)
        self._fav_btn.hide()
        self._is_favorite = is_favorite
        self._apply_favorite_style()

        # ---- Name zone: separate label, always visible, centered ---------- #
        self._title_label = ElidedLabel(title, self, max_lines=TITLE_MAX_LINES)
        self._title_label.setObjectName("CardTitle")
        self._title_label.setAlignment(Qt.AlignCenter)

        # Small square activation button (config cards only): aligned with
        # the name row, bottom-right. It never starts a card drag (it
        # consumes its own mouse events) and never changes the card size.
        self._activation_state = activation_state
        self._toggle_btn = QPushButton(self)
        self._toggle_btn.setObjectName("CardToggleButton")
        self._toggle_btn.setFixedSize(TOGGLE_SIZE, TOGGLE_SIZE)
        self._toggle_btn.setIconSize(QSize(18, 18))
        self._toggle_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self._toggle_btn.setContextMenuPolicy(Qt.DefaultContextMenu)
        self._toggle_btn.clicked.connect(self._on_toggle_clicked)
        self._apply_toggle_style()

        # Rangée du nom : le label prend TOUTE la largeur restante (stretch 1)
        # et le bouton reste épinglé à droite. Le titre est centré par le
        # label lui-même (paintEvent + AlignCenter), pas par des spacers :
        # des addStretch symétriques laissaient au label sa seule taille
        # « sizeHint » (largeur du mot le plus long) et absorbaient tout
        # l'espace disponible — d'où les titres réduits à une lettre.
        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(6)
        name_row.addWidget(self._title_label, 1)
        name_row.addWidget(self._toggle_btn, 0)

        self._subtitle_label = QLabel(subtitle, self)
        self._subtitle_label.setObjectName("CardSubtitle")
        self._subtitle_label.setAlignment(Qt.AlignCenter)
        self._subtitle_label.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        layout.addWidget(self._preview_zone)
        layout.addLayout(name_row)
        layout.addWidget(self._subtitle_label)

        # Rest position inside the cell (set by CardCell). This is a fixed
        # offset, never captured from pos(): the card is not layout-managed,
        # so this value can never go stale.
        self._base_pos = QPoint(0, 0)

        self._status = status
        self._apply_status()

        self._anim = QPropertyAnimation(self, b"lift", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    # ------------------------------------------------------------------ #
    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        """Position the overlays (status chip + favourite star) in the top
        corners of the preview zone. They never participate in the layout,
        so the title row keeps its full width."""
        super().resizeEvent(event)
        margin = 12
        if self._status_label.isVisible():
            self._status_label.adjustSize()
            self._status_label.move(
                margin + 4,
                margin + 4,
            )
        if self._fav_btn.isVisible():
            self._fav_btn.move(
                self.width() - margin - FAV_SIZE - 4,
                margin + 4,
            )

    # ------------------------------------------------------------------ #
    def sizeHint(self) -> QSize:
        """Never report a size smaller than the card's minimum, so the grid
        keeps columns wide enough (the placeholder is smaller without an
        image, but the card itself must not shrink below its minimum)."""
        hint = super().sizeHint()
        return QSize(
            max(hint.width(), self.minimumWidth()),
            max(hint.height(), self.minimumHeight()),
        )

    def set_base_pos(self, pos: QPoint) -> None:
        """Set the card's rest position (its origin inside the cell)."""
        self._base_pos = QPoint(pos)

    def get_lift(self) -> float:
        return self._lift

    def set_lift(self, value: float) -> None:
        self._lift = value
        # Move only inside the cell, around the fixed rest position.
        self.move(self._base_pos.x(), int(self._base_pos.y() - LIFT_PIXELS * value))

    lift = Property(float, get_lift, set_lift)

    # ------------------------------------------------------------------ #
    def _animate(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._lift)
        self._anim.setEndValue(target)
        self._anim.start()

    def enterEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._animate(0.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if event.button() == Qt.LeftButton:
            self._press_pos = event.position().toPoint()
            self._dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        """Left button held + moved beyond the drag threshold → start an
        internal card drag (reorder). A simple click never starts a drag
        (threshold), and the drag carries a custom MIME — never file URLs —
        so it can not collide with the file-import drop."""
        if (
            self._press_pos is not None
            and event.buttons() & Qt.LeftButton
            and not self._dragging
        ):
            delta = event.position().toPoint() - self._press_pos
            if delta.manhattanLength() >= QApplication.startDragDistance():
                self._start_drag()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        # A release right after a drag must not be treated as a click.
        was_dragging = self._dragging
        self._dragging = False
        self._press_pos = None
        if (
            event.button() == Qt.LeftButton
            and not was_dragging
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def _start_drag(self) -> None:
        """Start a QDrag with a light, semi-transparent card pixmap."""
        self._dragging = True
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(CARD_DRAG_MIME, self.drag_key.encode("utf-8"))
        drag.setMimeData(mime)
        pixmap = QPixmap(self.size())
        self.render(pixmap)
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
        drag.exec(Qt.MoveAction)

    def contextMenuEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        """Right-click: edit the card's image, or delete it (the item is
        moved to the Windows Recycle Bin by the caller after confirmation)."""
        menu = QMenu(self)
        action = menu.addAction(t("card.edit_image"))
        menu.addSeparator()
        delete_action = menu.addAction(t("common.delete"))
        chosen = menu.exec(event.globalPos())
        if chosen == action:
            self.edit_image_requested.emit()
        elif chosen == delete_action:
            self.delete_requested.emit()
        event.accept()

    # ------------------------------------------------------------------ #
    # Activation button (config cards)
    # ------------------------------------------------------------------ #
    def _on_toggle_clicked(self) -> None:
        """Le bouton ne fait que transmettre l'action : le contrôleur
        existant (MainWindow) exécute la même logique que le bouton
        Activer/Désactiver de la page de configuration."""
        self.toggle_activation_requested.emit()

    def _apply_toggle_style(self) -> None:
        """Mettre à jour l'apparence du bouton selon l'état réel connu.
        Actif = rouge discret + « X » ; sinon = accent + « ▶ »."""
        if self._activation_state is None:
            self._toggle_btn.hide()
            return
        self._toggle_btn.show()
        active = self._activation_state == "active"
        if active:
            self._toggle_btn.setStyleSheet(_toggle_qss(theme_color("danger"), "#fca5a5", "#dc2626", "#7f1d1d"))
            self._toggle_btn.setIcon(close_icon())
            self._toggle_btn.setToolTip(t("card.deactivate_tooltip"))
        else:
            accent = theme_color("accent")
            self._toggle_btn.setStyleSheet(
                _toggle_qss(accent, theme_color("accent_hover"), theme_color("accent_dark"), "#2b4b8a")
            )
            self._toggle_btn.setIcon(play_icon())
            self._toggle_btn.setToolTip(t("card.activate_tooltip"))

    # ------------------------------------------------------------------ #
    # Favourite star (v1.3.0)
    # ------------------------------------------------------------------ #
    def _on_favorite_clicked(self) -> None:
        """Le bouton ne fait que transmettre l'action : le contrôleur
        (MainWindow) bascule l'état et le persiste."""
        self.favorite_toggled.emit()

    def _apply_favorite_style(self) -> None:
        """Étoile pleine (favori) ou contour (non favori) — jamais d'emoji."""
        if self._is_favorite:
            self._fav_btn.setIcon(star_icon(filled=True, color="#fbbf24"))
            self._fav_btn.setToolTip(t("card.favorite_remove"))
        else:
            self._fav_btn.setIcon(star_icon(filled=False, color=theme_color("text_dim")))
            self._fav_btn.setToolTip(t("card.favorite_add"))

    def is_favorite(self) -> bool:
        """État favori actuel de la carte."""
        return bool(self._is_favorite)

    def set_favorite(self, favorite: bool) -> None:
        """Actualiser l'étoile après un basculement."""
        self._is_favorite = favorite
        self._apply_favorite_style()

    def show_favorite(self, enabled: bool) -> None:
        """Afficher/masquer l'étoile (config cards only)."""
        self._fav_btn.setVisible(enabled)
        if enabled:
            self._fav_btn.move(
                self.width() - 12 - FAV_SIZE - 4,
                12 + 4,
            )

    @property
    def favorite_button(self) -> QPushButton | None:
        """Le bouton étoile (``None`` pour les cartes non-config)."""
        if self._fav_btn.isHidden():
            return None
        return self._fav_btn

    # ------------------------------------------------------------------ #
    # Smart status (v1.3.0)
    # ------------------------------------------------------------------ #
    def _apply_status(self) -> None:
        """Affiche la puce de statut selon l'état réel de la configuration.
        ``None`` = aucune puce (cartes dossier/catégorie)."""
        if self._status is None:
            self._status_label.hide()
            return
        key, color = _STATUS_STYLES.get(
            self._status, ("card.status_ready", SUCCESS)
        )
        self._status_label.setText(t(key))
        self._status_label.setStyleSheet(
            f"border: none; background: transparent; color: {theme_color('text_dim')};"
            " font-size: 8pt; font-weight: 700; padding: 2px 4px;"
            f" border-left: 3px solid {color};"
        )
        self._status_label.show()
        self._status_label.adjustSize()
        self._status_label.move(12 + 4, 12 + 4)

    def set_status(self, status: str | None) -> None:
        """Actualiser la puce (après une activation, par exemple)."""
        self._status = status
        self._apply_status()

    def set_activation_state(self, state: str | None) -> None:
        """Actualiser le bouton après une activation/désactivation (l'état
        provient toujours de la source de vérité, jamais d'une supposition)."""
        self._activation_state = state
        self._apply_toggle_style()

    def set_toggle_busy(self, busy: bool) -> None:
        """Désactiver temporairement le bouton pendant une opération pour
        empêcher toute double activation concurrente."""
        self._toggle_btn.setEnabled(not busy)

    @property
    def toggle_button(self) -> QPushButton | None:
        """Le bouton d'activation (``None`` pour les cartes non-config)."""
        if self._activation_state is None:
            return None
        return self._toggle_btn
