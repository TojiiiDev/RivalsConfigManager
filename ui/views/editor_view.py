"""Editor Mode view — hierarchical navigation for preview management.

A two-panel page: the left shows a navigable tree (category → subcategory →
weapon → skin / config), the right shows the selected element's current
preview and lets the user add/replace or remove it.

The breadcrumb above the list always shows the current position and each
segment is clickable for instant navigation back to any level.

Nothing is written until the user confirms — « Cancel » discards the
pending choice.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t
from app.models import ConfigItem, Node
from ui.theme import DANGER, SUCCESS, TEXT_DIM
from ui.widgets.preview import PreviewLabel

#: Any element that can be displayed and edited in the detail panel.
EditableTarget = Node | ConfigItem

#: Reuse the existing image filter (PNG/JPG/JPEG/WEBP/BMP).
IMAGE_FILTER = t("image.filter")


class _ClickableLabel(QLabel):
    """A QLabel that emits ``clicked`` on mouse press."""

    clicked = Signal()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


def _breadcrumb_label(text: str, clickable: bool, parent=None) -> QLabel:
    """A small styled label for the breadcrumb bar."""
    if clickable:
        label = _ClickableLabel(text, parent)
        label.setStyleSheet(
            "color: #4f8cff; border: none; background: transparent;"
            " font-size: 9pt; font-weight: 600;"
        )
        label.setCursor(Qt.PointingHandCursor)
    else:
        label = QLabel(text, parent)
        label.setObjectName("CardSubtitle")
        label.setStyleSheet(
            f"color: {TEXT_DIM}; border: none; background: transparent;"
            f" font-size: 9pt;"
        )
    return label


def _separator_label(parent=None) -> QLabel:
    sep = QLabel("›", parent)
    sep.setStyleSheet(
        f"color: {TEXT_DIM}; border: none; background: transparent;"
        f" font-size: 9pt; padding: 0 2px;"
    )
    return sep


class EditorView(QWidget):
    """The Editor Mode page. Emits ``integrate_requested`` /
    ``remove_requested`` so the main window owns the actual integration
    + refresh (same pattern as every other view)."""

    integrate_requested = Signal(object, str)  # target, source path
    remove_requested = Signal(object)          # target

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PageRoot")

        self._root_node: Node | None = None
        #: Stack of visited nodes for the breadcrumb/back navigation.
        self._stack: list[Node] = []
        #: Currently selected item — can be a Node (category) or ConfigItem.
        self._current: EditableTarget | None = None
        self._selected_path: str | None = None
        self._pending_source: Path | None = None

        # ---- Header ------------------------------------------------------ #
        self._title = QLabel("", self)
        self._title.setObjectName("PageTitle")
        self._subtitle = QLabel("", self)
        self._subtitle.setObjectName("PageSubtitle")
        self._subtitle.setWordWrap(True)

        # ---- Breadcrumb -------------------------------------------------- #
        self._breadcrumb_container = QWidget(self)
        self._breadcrumb_layout = QHBoxLayout(self._breadcrumb_container)
        self._breadcrumb_layout.setContentsMargins(0, 0, 0, 0)
        self._breadcrumb_layout.setSpacing(0)
        self._breadcrumb_layout.addStretch(1)

        # ---- Search ------------------------------------------------------- #
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._filter)

        # ---- Left: navigation list --------------------------------------- #
        self._list = QListWidget(self)
        self._list.currentItemChanged.connect(self._on_select)
        self._list.itemDoubleClicked.connect(self._on_double_click)

        # ---- Right: detail ------------------------------------------------ #
        self._detail_name = QLabel("", self)
        self._detail_name.setObjectName("PageTitle")
        self._detail_name.setWordWrap(True)
        self._detail_type = QLabel("", self)
        self._detail_type.setObjectName("SectionLabel")
        self._detail_path = QLabel("", self)
        self._detail_path.setObjectName("PathLabel")
        self._detail_path.setWordWrap(True)

        self._preview = PreviewLabel(280, self)
        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.setMinimumHeight(24)

        self._add_replace_btn = QPushButton("", self)
        self._add_replace_btn.setObjectName("PrimaryButton")
        self._add_replace_btn.clicked.connect(self._choose_image)
        self._integrate_btn = QPushButton("", self)
        self._integrate_btn.setObjectName("PrimaryButton")
        self._integrate_btn.clicked.connect(self._integrate)
        self._cancel_btn = QPushButton("", self)
        self._cancel_btn.clicked.connect(self._cancel_pending)
        self._remove_btn = QPushButton("", self)
        self._remove_btn.setObjectName("DangerButton")
        self._remove_btn.clicked.connect(self._remove)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self._add_replace_btn)
        actions.addWidget(self._integrate_btn)
        actions.addWidget(self._cancel_btn)
        actions.addStretch(1)
        actions.addWidget(self._remove_btn)

        detail = QWidget(self)
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        detail_layout.setSpacing(10)
        detail_layout.addWidget(self._detail_name)
        detail_layout.addWidget(self._detail_type)
        detail_layout.addWidget(self._detail_path)
        detail_layout.addWidget(self._preview, 0, Qt.AlignHCenter)
        detail_layout.addWidget(self._status)
        detail_layout.addLayout(actions)
        detail_layout.addStretch(1)
        self._detail = detail

        # ---- Split layout -------------------------------------------------- #
        left = QWidget(self)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        left_layout.addWidget(self._breadcrumb_container)
        left_layout.addWidget(self._search)
        left_layout.addWidget(self._list, 1)

        splitter = QSplitter(Qt.Horizontal, self)
        splitter.addWidget(left)
        splitter.addWidget(detail)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        splitter.setChildrenCollapsible(False)

        self.retranslate()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 24, 40, 20)
        layout.setSpacing(14)
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)
        layout.addWidget(splitter, 1)

        self._reset_detail()

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        """Apply the current language to every static text."""
        self._title.setText(t("editor.title"))
        self._subtitle.setText(t("editor.subtitle"))
        self._search.setPlaceholderText(t("editor.search_placeholder"))
        self._add_replace_btn.setText(t("editor.add_replace_image"))
        self._integrate_btn.setText(t("editor.integrate"))
        self._cancel_btn.setText(t("editor.cancel"))
        self._remove_btn.setText(t("editor.remove"))
        self._refresh_detail()

    # ------------------------------------------------------------------ #
    # Library / navigation
    # ------------------------------------------------------------------ #
    def set_library(self, root: Node | None) -> None:
        """Reset the editor to the library root (full rescan)."""
        self._root_node = root
        self._stack = []
        self._current = None
        self._selected_path = None
        self._pending_source = None
        self._update_breadcrumb()
        self._update_list()

    def _enter_folder(self, node: Node) -> None:
        """Navigate into a folder, pushing onto the stack."""
        self._stack.append(node)
        self._current = None
        self._pending_source = None
        self._selected_path = None
        self._update_breadcrumb()
        self._update_list()

    def _go_back(self, target: Node | None = None) -> None:
        """Navigate back to ``target`` (or one level up if None)."""
        if target is None:
            if len(self._stack) > 1:
                self._stack.pop()
            else:
                self._stack.clear()
        else:
            # Pop until we find target, or clear if not found.
            while self._stack and self._stack[-1] is not target:
                self._stack.pop()
            if self._stack:
                self._stack.pop()  # remove target itself too
        self._current = None
        self._pending_source = None
        self._selected_path = None
        self._update_breadcrumb()
        self._update_list()

    def _current_folder(self) -> Node | None:
        """The node currently being displayed (root if at top level)."""
        return self._stack[-1] if self._stack else self._root_node

    # ------------------------------------------------------------------ #
    # Breadcrumb
    # ------------------------------------------------------------------ #
    def _update_breadcrumb(self) -> None:
        """Rebuild the breadcrumb bar from the current stack."""
        # Clear existing widgets.
        while self._breadcrumb_layout.count():
            item = self._breadcrumb_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            spacer = item.spacerItem()
            if spacer is not None:
                self._breadcrumb_layout.removeItem(spacer)

        root = self._root_node
        if root is None:
            self._breadcrumb_layout.addStretch(1)
            return

        # Root label (always present, clickable to go to root).
        root_lbl = _breadcrumb_label(root.name, clickable=True)
        root_lbl.clicked.connect(lambda: self._go_back(None))
        self._breadcrumb_layout.addWidget(root_lbl)

        for i, node in enumerate(self._stack):
            self._breadcrumb_layout.addWidget(_separator_label())
            is_last = i == len(self._stack) - 1
            lbl = _breadcrumb_label(node.name, clickable=not is_last)
            if is_last:
                lbl.setStyleSheet(
                    f"color: {TEXT_DIM}; border: none; background: transparent;"
                    f" font-size: 9pt;"
                )
            else:
                captured_node = node
                lbl.clicked.connect(
                    lambda _=False, n=captured_node: self._go_back(n)
                )
            self._breadcrumb_layout.addWidget(lbl)

        self._breadcrumb_layout.addStretch(1)

    # ------------------------------------------------------------------ #
    # List
    # ------------------------------------------------------------------ #
    def _update_list(self) -> None:
        """Populate the list with children of the current folder.

        After populating, the first item is selected and the detail panel
        is refreshed — even for a single-element list where Qt would
        normally suppress the ``currentItemChanged`` signal.
        """
        folder = self._current_folder()
        query = self._search.text().strip().lower()
        selected = self._selected_path
        self._list.blockSignals(True)
        self._list.clear()

        if folder is None:
            self._list.blockSignals(False)
            self._reset_detail()
            return

        items: list[Node | ConfigItem] = []
        for sub in folder.subdirs:
            if query and query not in sub.name.lower():
                continue
            items.append(sub)
        for cfg in folder.configs:
            if query and query not in cfg.name.lower():
                continue
            items.append(cfg)

        if not items and query:
            hint = QListWidgetItem(t("editor.no_results"))
            hint.setFlags(Qt.NoItemFlags)
            self._list.addItem(hint)
        elif not items:
            hint = QListWidgetItem(t("editor.empty_folder"))
            hint.setFlags(Qt.NoItemFlags)
            self._list.addItem(hint)
        else:
            for item in items:
                list_item = QListWidgetItem(self._item_label(item))
                list_item.setData(Qt.UserRole, item)
                self._list.addItem(list_item)
                if selected is not None and str(item.path) == selected:
                    self._list.setCurrentItem(list_item)

        self._list.blockSignals(False)

        # Ensure the first item is always selected, even when Qt would
        # suppress the signal (single-element list, same index as before).
        if self._list.currentItem() is None and self._list.count():
            self._list.setCurrentRow(0)

        # Explicitly drive the detail panel from the current selection.
        # This covers the case where signals were suppressed or the item
        # was already at the same index.
        current_item = self._list.currentItem()
        if current_item is not None:
            target = current_item.data(Qt.UserRole)
            if target is not None:
                self._current = target
                self._selected_path = str(target.path)
                self._pending_source = None
                self._refresh_detail()
        else:
            self._current = None
            self._selected_path = None
            self._reset_detail()

    def _item_label(self, item: Node | ConfigItem) -> str:
        if isinstance(item, ConfigItem):
            kind = t("editor.item_type_config")
        else:
            kind = t("editor.item_type_folder")
        return f"{item.name}   ({kind})"

    def _filter(self) -> None:
        self._update_list()

    # ------------------------------------------------------------------ #
    # Selection / interaction
    # ------------------------------------------------------------------ #
    def _on_select(self, current: QListWidgetItem | None, _previous=None) -> None:
        """Handle list selection — works for both Node and ConfigItem."""
        if current is None:
            self._current = None
            self._selected_path = None
            self._reset_detail()
            return
        item = current.data(Qt.UserRole)
        if item is None:
            # hint item (no_results / empty_folder)
            self._current = None
            self._selected_path = None
            self._reset_detail()
            return
        self._current = item
        self._selected_path = str(item.path)
        self._pending_source = None
        self._refresh_detail()

    def _on_double_click(self, item: QListWidgetItem) -> None:
        """Double-click on a Node navigates into it."""
        target = item.data(Qt.UserRole)
        if isinstance(target, Node):
            self._enter_folder(target)

    # ------------------------------------------------------------------ #
    # Detail panel
    # ------------------------------------------------------------------ #
    def _refresh_detail(self) -> None:
        if self._current is None:
            self._reset_detail()
            return
        item = self._current
        self._detail_name.setText(item.name)
        if isinstance(item, ConfigItem):
            self._detail_type.setText(t("editor.item_type_config"))
        else:
            self._detail_type.setText(t("editor.item_type_folder"))
        self._detail_path.setText(str(item.path))

        has_preview = item.preview is not None
        if self._pending_source is not None:
            self._preview.set_path(self._pending_source, item.name)
            self._set_status(t("editor.pending_preview"), "info")
        else:
            self._preview.set_path(item.preview, item.name)
            self._set_status(
                t("editor.current_preview") if has_preview else t("editor.no_preview"),
                "ok" if has_preview else "info",
            )

        # Add/Replace is ALWAYS active when an element is selected.
        self._add_replace_btn.setEnabled(True)
        self._integrate_btn.setVisible(self._pending_source is not None)
        self._cancel_btn.setVisible(self._pending_source is not None)
        self._remove_btn.setVisible(has_preview)
        self._detail.setVisible(True)

    def _reset_detail(self) -> None:
        self._detail_name.setText("")
        self._detail_type.setText("")
        self._detail_path.setText("")
        self._preview.set_path(None, "?")
        self._set_status(t("editor.select_hint"), "info")
        self._add_replace_btn.setEnabled(False)
        self._integrate_btn.hide()
        self._cancel_btn.hide()
        self._remove_btn.hide()
        self._detail.setVisible(False)
        self._pending_source = None

    def _set_status(self, text: str, kind: str) -> None:
        color = {"ok": SUCCESS, "error": DANGER}.get(kind, TEXT_DIM)
        self._status.setStyleSheet(
            f"color: {color}; border: none; background: transparent;"
        )
        self._status.setText(text)

    # ------------------------------------------------------------------ #
    # Image operations
    # ------------------------------------------------------------------ #
    def _choose_image(self) -> None:
        if self._current is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, t("editor.choose_image"), str(Path.home()), IMAGE_FILTER
        )
        if not path:
            return
        self._pending_source = Path(path)
        self._refresh_detail()

    def _integrate(self) -> None:
        if self._current is not None and self._pending_source is not None:
            self.integrate_requested.emit(self._current, str(self._pending_source))

    def _cancel_pending(self) -> None:
        self._pending_source = None
        self._refresh_detail()

    def _remove(self) -> None:
        if self._current is not None:
            self.remove_requested.emit(self._current)

    # ------------------------------------------------------------------ #
    # Public helpers for MainWindow
    # ------------------------------------------------------------------ #
    def set_error(self, message: str) -> None:
        """Show an integration error."""
        self._set_status(f"\u2718 {message}", "error")

    def show_success(self, message: str) -> None:
        """Show a success message."""
        self._set_status(f"\u2714 {message}", "ok")

    def clear_pending(self) -> None:
        """Clear the pending choice after a successful integration."""
        self._pending_source = None
        self._refresh_detail()
