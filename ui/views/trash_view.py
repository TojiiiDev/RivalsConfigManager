"""Trash (corbeille) view: browse, search, restore or permanently delete.

The trash is the application's own internal trash: entries are stored
(never used) and stay visible here until the user restores or permanently
deletes them. A search bar filters the list in memory — case-insensitive,
spaces normalized, partial match, instant — without ever writing anything.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.categories import category_rank
from app.i18n import t
from app.trash import TrashEntry


def _human_size(size: int) -> str:
    """Taille lisible (octets → Ko/Mo)."""
    if size < 1024:
        return t("size.bytes", size=size)
    if size < 1024 * 1024:
        return t("size.kb", size=f"{size / 1024:.1f}")
    return t("size.mb", size=f"{size / (1024 * 1024):.1f}")


class TrashView(QWidget):
    restore_clicked = Signal(object)   # TrashEntry
    destroy_clicked = Signal(object)   # TrashEntry
    empty_clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PageRoot")

        self._title = QLabel("", self)
        self._title.setObjectName("PageTitle")
        self._subtitle = QLabel("", self)
        self._subtitle.setObjectName("PageSubtitle")
        self._subtitle.setWordWrap(True)

        # ---- Recherche (filtrage en mémoire uniquement) ---------------- #
        self._search = QLineEdit(self)
        self._search.setPlaceholderText("")
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._apply_filter)

        self._results_label = QLabel("", self)
        self._results_label.setObjectName("PageSubtitle")

        self._sort = QComboBox(self)
        self._sort.currentTextChanged.connect(self._apply_sort)
        self._sort_keys = ("date", "name", "category")

        self._list = QListWidget(self)
        self._list.itemSelectionChanged.connect(self._update_buttons)

        self._restore_btn = QPushButton("", self)
        self._restore_btn.setToolTip("")
        self._restore_btn.clicked.connect(self._on_restore)

        self._destroy_btn = QPushButton("", self)
        self._destroy_btn.setObjectName("DangerButton")
        self._destroy_btn.setToolTip("")
        self._destroy_btn.clicked.connect(self._on_destroy)

        self._empty_btn = QPushButton("", self)
        self._empty_btn.setObjectName("DangerButton")
        self._empty_btn.setToolTip("")
        self._empty_btn.clicked.connect(self.empty_clicked)

        self._empty_label = QLabel("", self)
        self._empty_label.setObjectName("PageSubtitle")
        self._empty_label.setAlignment(Qt.AlignCenter)
        self._empty_label.hide()

        # État initial (avant retranslate, qui filtre la liste vide).
        self._entries: list[TrashEntry] = []
        self._query = ""
        self.retranslate()

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self._sort)
        actions.addStretch(1)
        actions.addWidget(self._restore_btn)
        actions.addWidget(self._destroy_btn)
        actions.addWidget(self._empty_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 24, 40, 24)
        layout.setSpacing(12)
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)
        layout.addWidget(self._search)
        layout.addWidget(self._results_label)
        layout.addLayout(actions)
        layout.addWidget(self._list, 1)
        layout.addWidget(self._empty_label, 1)

        self._update_buttons()

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        """Apply the current language to every static text (hot switch)."""
        self._title.setText(t("trash.title"))
        self._search.setPlaceholderText(t("trash.search_placeholder"))
        self._restore_btn.setText(t("trash.restore"))
        self._restore_btn.setToolTip(t("trash.restore_tooltip"))
        self._destroy_btn.setText(t("trash.destroy"))
        self._destroy_btn.setToolTip(t("trash.destroy_tooltip"))
        self._empty_btn.setText(t("trash.empty"))
        self._empty_btn.setToolTip(t("trash.empty_tooltip"))
        self._empty_label.setText(t("trash.empty_label"))
        # Rebuild the sort combo, keeping the current selection.
        current = self._sort.currentData()
        labels = (
            t("trash.sort_date"),
            t("trash.sort_name"),
            t("trash.sort_category"),
        )
        self._sort.blockSignals(True)
        self._sort.clear()
        for key, label in zip(self._sort_keys, labels):
            self._sort.addItem(label, key)
        index = self._sort.findData(current)
        self._sort.setCurrentIndex(index if index >= 0 else 0)
        self._sort.blockSignals(False)
        self._apply_filter()

    # ------------------------------------------------------------------ #
    def set_entries(self, entries: list[TrashEntry]) -> None:
        self._entries = list(entries)
        self._apply_filter()

    # ------------------------------------------------------------------ #
    def _apply_filter(self, text: str | None = None) -> None:
        """Filtrage visuel en mémoire (aucune écriture, aucun rescan) : les
        éléments qui ne correspondent pas sont masqués, jamais supprimés."""
        if text is not None:
            self._query = text
        normalized = " ".join(self._query.split()).casefold()
        if not normalized:
            visible = list(self._entries)
        else:
            visible = [
                e
                for e in self._entries
                if normalized
                in " ".join(
                    [e.name, e.category or "", e.weapon or "", str(e.original_path)]
                ).casefold()
            ]
        self._visible = visible
        if self._query.strip():
            if visible:
                n = len(visible)
                self._results_label.setText(
                    t("search.results_count_one", count=n)
                    if n == 1
                    else t("search.results_count_many", count=n)
                )
            else:
                self._results_label.setText(t("trash.no_results"))
        else:
            self._results_label.setText("")
        self._apply_sort()

    # ------------------------------------------------------------------ #
    def _apply_sort(self) -> None:
        entries = list(self._visible)
        sort_key = self._sort.currentData()
        if sort_key == "name":
            entries.sort(key=lambda e: e.name.casefold())
        elif sort_key == "category":
            # Ordre canonique des catégories, puis le reste par nom.
            def cat_key(e: TrashEntry) -> tuple:
                rank = category_rank(e.category or "")
                return (9 if rank is None else rank, e.name.casefold())

            entries.sort(key=cat_key)
        else:
            entries.sort(key=lambda e: e.created, reverse=True)

        self._list.clear()
        for entry in entries:
            item = QListWidgetItem(self._item_label(entry))
            item.setData(Qt.UserRole, entry)
            item.setToolTip(str(entry.original_path))
            self._list.addItem(item)

        n = len(entries)
        if not self._query.strip():
            suffix = "s" if n != 1 else ""
            self._subtitle.setText(
                t("trash.subtitle", count=n, s=suffix)
            )
        self._list.setVisible(bool(entries))
        self._empty_label.setVisible(not entries and not self._query.strip())
        self._empty_btn.setEnabled(bool(entries))
        self._update_buttons()

    # ------------------------------------------------------------------ #
    def _item_label(self, entry: TrashEntry) -> str:
        kind = t("unit.configuration") if entry.kind == "file" else t("unit.folder_one")
        bits = [
            entry.name,
            f"{kind}",
            _human_size(entry.size),
            entry.label,
        ]
        if entry.category:
            bits.append(entry.category)
        if entry.weapon:
            bits.append(entry.weapon)
        return "  ·  ".join(bits)

    def _selected_entry(self) -> TrashEntry | None:
        current = self._list.currentItem()
        if current is None:
            return None
        return current.data(Qt.UserRole)

    def _update_buttons(self) -> None:
        has = self._selected_entry() is not None
        self._restore_btn.setEnabled(has)
        self._destroy_btn.setEnabled(has)

    def _on_restore(self) -> None:
        entry = self._selected_entry()
        if entry is not None:
            self.restore_clicked.emit(entry)

    def _on_destroy(self) -> None:
        entry = self._selected_entry()
        if entry is not None:
            self.destroy_clicked.emit(entry)
