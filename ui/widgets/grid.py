"""A scrollable grid of cards that reflows when the window is resized.

Each card lives inside a :class:`CardCell`. The cell is what the QGridLayout
manages; the card is positioned manually inside its cell, so the hover lift
animation never fights the layout and can never move a card out of its slot.

Cards can be reordered by drag & drop: the drag carries a custom MIME type
(never file URLs), so reordering can never trigger the file-import drop. The
order is reported through :attr:`CardGrid.order_changed` and persisted by the
caller (settings.json) — the library files are never touched.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtWidgets import QGridLayout, QScrollArea, QWidget

from .card import CARD_DRAG_MIME, Card, LIFT_PIXELS


@dataclass
class CardSpec:
    title: str
    subtitle: str
    preview: Path | None
    on_click: object  # callable
    edit_target: object | None = None  # Node or ConfigItem whose image to edit
    delete_target: object | None = None  # Node or ConfigItem to delete (recycle bin)
    key: str = ""  # stable identity for drag & drop reordering
    #: Activation button: target ConfigItem + initial state from the real
    #: Fleasion source of truth ("active"/"copied"/"inactive"; None = no
    #: button, e.g. folder/category cards).
    activation_target: object | None = None
    activation_state: str | None = None
    #: Favourite star (v1.3.0): initial state + the ConfigItem it toggles.
    is_favorite: bool = False
    favorite_target: object | None = None
    #: Smart status chip (v1.3.0): "ready"/"incomplete"/"error"/"active"
    #: or None (no chip — folder/category cards).
    status: str | None = None


class CardCell(QWidget):
    """A grid cell holding one card.

    The card fills the cell with a small top margin that provides the
    headroom for the hover lift. The card is positioned manually (it is not
    inside a layout), so its rest position is always exactly ``(0, TOP)``
    and the lift animation only ever moves it within the cell.
    """

    #: Top margin (px) reserved inside the cell for the hover lift.
    TOP_MARGIN = LIFT_PIXELS + 1

    def __init__(self, card: Card, parent=None) -> None:
        super().__init__(parent)
        self._card = card
        card.setParent(self)
        self._place_card()

    # ------------------------------------------------------------------ #
    def _place_card(self) -> None:
        self._card.set_base_pos(QPoint(0, self.TOP_MARGIN))
        self._card.setGeometry(
            0,
            self.TOP_MARGIN,
            self.width(),
            max(0, self.height() - self.TOP_MARGIN),
        )

    def sizeHint(self) -> QSize:
        hint = self._card.sizeHint()
        if hint.isValid():
            return QSize(hint.width(), hint.height() + self.TOP_MARGIN)
        return QSize(180, 210 + self.TOP_MARGIN)

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._place_card()

    @property
    def card(self) -> Card:
        return self._card


class CardGrid(QScrollArea):
    """Scroll area whose content is a responsive grid of cards.

    Drag & drop: cards can be reordered when :attr:`reorderable` is True.
    The insertion position is highlighted on the target cell while dragging;
    dropping emits :attr:`order_changed` with the new order of card keys.
    """

    edit_image_requested = Signal(object)  # Node or ConfigItem
    delete_requested = Signal(object)       # Node or ConfigItem
    toggle_activation_requested = Signal(object)  # ConfigItem
    favorite_toggled = Signal(object)       # ConfigItem
    order_changed = Signal(list)            # list[str] — new order of keys

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setAcceptDrops(True)

        self._container = QWidget(self)
        self._grid = QGridLayout(self._container)
        self._grid.setContentsMargins(4, 4, 16, 16)
        self._grid.setHorizontalSpacing(14)
        self._grid.setVerticalSpacing(14)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.setWidget(self._container)

        self._cells: list[CardCell] = []
        self._cards: list[Card] = []
        self.reorderable = True
        self._drop_target = -1

    # ------------------------------------------------------------------ #
    def set_cards(self, specs: list[CardSpec]) -> None:
        # Clear previous content (cells own their cards).
        for cell in self._cells:
            cell.setParent(None)
            cell.deleteLater()
        self._cells = []
        self._cards = []
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._drop_target = -1

        for spec in specs:
            card = Card(
                spec.title,
                spec.subtitle,
                spec.preview,
                key=spec.key,
                activation_state=spec.activation_state,
                is_favorite=spec.is_favorite,
                status=spec.status,
            )
            card.clicked.connect(spec.on_click)
            if spec.edit_target is not None:
                card.edit_image_requested.connect(
                    lambda t=spec.edit_target: self.edit_image_requested.emit(t)
                )
            if spec.delete_target is not None:
                card.delete_requested.connect(
                    lambda t=spec.delete_target: self.delete_requested.emit(t)
                )
            if spec.activation_target is not None:
                card.toggle_activation_requested.connect(
                    lambda t=spec.activation_target: self.toggle_activation_requested.emit(t)
                )
            if spec.favorite_target is not None:
                card.show_favorite(True)
                card.favorite_toggled.connect(
                    lambda t=spec.favorite_target: self.favorite_toggled.emit(t)
                )
            else:
                card.show_favorite(False)
            cell = CardCell(card, self._container)
            self._cells.append(cell)
            self._cards.append(card)

        self._relayout()

    # ------------------------------------------------------------------ #
    def set_reorderable(self, enabled: bool) -> None:
        """Enable/disable drag & drop reordering (search results keep it off)."""
        self.reorderable = bool(enabled)

    # ------------------------------------------------------------------ #
    def _relayout(self) -> None:
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item.widget():
                self._grid.removeWidget(item.widget())
        if not self._cells:
            return

        width = self.viewport().width() or 800
        columns = max(1, width // 205)
        for index, cell in enumerate(self._cells):
            row, col = divmod(index, columns)
            self._grid.addWidget(cell, row, col)
        self._container.adjustSize()

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        super().resizeEvent(event)
        self._relayout()

    # ------------------------------------------------------------------ #
    # Drag & drop (reorder only — never file import)
    # ------------------------------------------------------------------ #
    def dragEnterEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if self.reorderable and event.mimeData().hasFormat(CARD_DRAG_MIME):
            self._drop_target = -1
            event.acceptProposedAction()
        else:
            event.ignore()  # file drops keep propagating to the import zone

    def dragMoveEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if self.reorderable and event.mimeData().hasFormat(CARD_DRAG_MIME):
            self._set_drop_target(self._index_at(event.position().toPoint()))
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        self._set_drop_target(-1)
        event.accept()

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        if not (self.reorderable and event.mimeData().hasFormat(CARD_DRAG_MIME)):
            event.ignore()
            return
        key = bytes(event.mimeData().data(CARD_DRAG_MIME)).decode("utf-8")
        target = self._index_at(event.position().toPoint())
        self._set_drop_target(-1)
        self.move_card(key, target)
        event.acceptProposedAction()

    def move_card(self, key: str, target_index: int) -> None:
        """Move the card identified by ``key`` so it lands at
        ``target_index`` (the insertion slot), then emit ``order_changed``.
        Display-only: library files are never touched."""
        if not self.reorderable:
            return
        source = self._find_index(key)
        if source < 0:
            return
        self._cells.insert(target_index, self._cells.pop(source))
        self._cards.insert(target_index, self._cards.pop(source))
        self._relayout()
        self.order_changed.emit([c.drag_key for c in self._cards])

    # ------------------------------------------------------------------ #
    def _find_index(self, key: str) -> int:
        for i, card in enumerate(self._cards):
            if card.drag_key == key:
                return i
        return -1

    # ------------------------------------------------------------------ #
    def find_card(self, key: str) -> Card | None:
        """The card whose stable key matches (path of the item)."""
        for card in self._cards:
            if card.drag_key == key:
                return card
        return None

    def set_card_activation_state(self, key: str, state: str | None) -> None:
        """Mettre à jour le bouton d'une carte après une opération (état réel)."""
        card = self.find_card(key)
        if card is not None:
            card.set_activation_state(state)

    def set_card_toggle_busy(self, key: str, busy: bool) -> None:
        """Désactiver/réactiver le bouton d'une carte pendant une opération."""
        card = self.find_card(key)
        if card is not None:
            card.set_toggle_busy(busy)

    def set_card_favorite(self, key: str, favorite: bool) -> None:
        """Actualiser l'étoile d'une carte après un basculement."""
        card = self.find_card(key)
        if card is not None:
            card.set_favorite(favorite)

    def set_card_status(self, key: str, status: str | None) -> None:
        """Actualiser la puce de statut d'une carte (après une action)."""
        card = self.find_card(key)
        if card is not None:
            card.set_status(status)

    def _index_at(self, pos: QPoint) -> int:
        """Insertion index for a drop at ``pos`` (container coordinates)."""
        if not self._cells:
            return 0
        for i, cell in enumerate(self._cells):
            rect = QRect(cell.mapTo(self._container, QPoint(0, 0)), cell.size())
            if rect.contains(pos):
                # Drop on the right half → insert after this cell.
                return i + 1 if pos.x() > rect.center().x() else i
        # Past the last card (or empty area below) → append.
        return len(self._cells)

    def _set_drop_target(self, index: int) -> None:
        """Highlight the cell where the dragged card would land (light)."""
        if index == self._drop_target:
            return
        if 0 <= self._drop_target < len(self._cells):
            self._cells[self._drop_target].setProperty("drop-target", False)
        self._drop_target = index
        if 0 <= index < len(self._cells):
            self._cells[index].setProperty("drop-target", True)
        for cell in self._cells:
            cell.style().unpolish(cell)
            cell.style().polish(cell)
