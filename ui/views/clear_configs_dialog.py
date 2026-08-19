"""« Clear Configs » selection dialog.

Lists the **real** configurations present in Fleasion's active folder
(``configs/``) with a checkbox each. Nothing is deleted when a box is
checked: the user selects, reviews the count, then confirms with
« Mettre à la Corbeille » — the actual move happens in the main window /
``FleasionManager.clear_configs``.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t


class ClearConfigsDialog(QDialog):
    """Pick which Fleasion configurations to move to the Windows Recycle
    Bin. ``selected`` is read after ``exec()`` returns ``Accepted``."""

    def __init__(self, configs: list[str], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("home.clear_configs"))
        self.setMinimumWidth(460)
        self.setMinimumHeight(380)

        title = QLabel("CLEAR CONFIGS", self)
        title.setObjectName("SectionLabel")
        note = QLabel(t("clear_configs.note"), self)
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)

        # ---- Search bar (visual filter only, in-memory) ---------------- #
        self._search = QLineEdit(self)
        self._search.setPlaceholderText(t("trash.search_placeholder"))
        self._search.setClearButtonEnabled(True)  # petite croix quand du texte
        self._search.textChanged.connect(self._apply_filter)

        self._results_label = QLabel("", self)
        self._results_label.setObjectName("PageSubtitle")

        # ---- Scrollable checkbox list ---------------------------------- #
        self._checkboxes: dict[str, QCheckBox] = {}
        list_widget = QWidget(self)
        list_layout = QVBoxLayout(list_widget)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(6)
        for name in configs:
            box = QCheckBox(name, list_widget)
            box.toggled.connect(self._update)
            list_layout.addWidget(box)
            self._checkboxes[name] = box
        list_layout.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(list_widget)

        self._select_all = QCheckBox("", self)
        self._select_all.toggled.connect(self._on_select_all)
        self._select_all.setText(t("clear_configs.select_all"))

        self._count_label = QLabel("", self)
        self._count_label.setObjectName("PageSubtitle")

        #: Les configs actuellement visibles après filtrage (la recherche ne
        #: supprime rien : les cases masquées gardent leur état).
        self._visible: list[str] = list(configs)

        # ---- Actions ----------------------------------------------------- #
        self._action_btn = QPushButton("", self)
        self._action_btn.setObjectName("PrimaryButton")
        self._action_btn.clicked.connect(self.accept)
        self._action_btn.setEnabled(False)
        self._action_btn.setText(t("clear_configs.action"))

        cancel_btn = QPushButton(t("common.cancel"), self)
        cancel_btn.clicked.connect(self.reject)

        bottom = QHBoxLayout()
        bottom.setSpacing(10)
        bottom.addStretch(1)
        bottom.addWidget(cancel_btn)
        bottom.addWidget(self._action_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(note)
        layout.addWidget(self._search)
        layout.addWidget(self._results_label)
        layout.addWidget(self._select_all)
        layout.addWidget(scroll, 1)
        layout.addWidget(self._count_label)
        layout.addLayout(bottom)

        # Compteur de résultats initial (recherche vide : toutes les configs).
        self._apply_filter("")

    # ------------------------------------------------------------------ #
    @property
    def selected(self) -> list[str]:
        """Les configurations cochées, dans l'ordre de la liste. Les cases
        masquées par la recherche gardent leur état : une config déjà
        cochée reste sélectionnée même si elle n'est plus visible."""
        return [name for name, box in self._checkboxes.items() if box.isChecked()]

    # ------------------------------------------------------------------ #
    def _apply_filter(self, text: str | None = None) -> None:
        """Filtre visuel en mémoire (aucune écriture, aucun rescan) : les
        cases qui ne correspondent pas sont masquées, jamais supprimées."""
        query = self._search.text() if text is None else text
        normalized = " ".join(query.split()).casefold()
        visible: list[str] = []
        for name, box in self._checkboxes.items():
            shown = (not normalized) or normalized in " ".join(name.split()).casefold()
            box.setVisible(shown)
            if shown:
                visible.append(name)
        self._visible = visible
        if visible:
            n = len(visible)
            self._results_label.setText(
                t("search.results_count_one", count=n)
                if n == 1
                else t("search.results_count_many", count=n)
            )
        else:
            self._results_label.setText(t("trash.no_results"))
        self._update()

    def _update(self) -> None:
        count = len(self.selected)
        self._count_label.setText(
            t("clear_configs.selected_count_one", count=count)
            if count == 1
            else t("clear_configs.selected_count_many", count=count)
        )
        self._action_btn.setEnabled(count > 0)
        # « Tout sélectionner » reflète l'état des configs **visibles**
        # (signaux bloqués pour ne pas re-déclencher le toggle en boucle).
        visible_boxes = [self._checkboxes[n] for n in self._visible]
        all_visible_checked = bool(visible_boxes) and all(
            b.isChecked() for b in visible_boxes
        )
        self._select_all.blockSignals(True)
        self._select_all.setChecked(all_visible_checked)
        self._select_all.blockSignals(False)

    def _on_select_all(self, checked: bool) -> None:
        """Agit UNIQUEMENT sur les configurations actuellement visibles
        après filtrage (jamais sur celles masquées par la recherche)."""
        for name in self._visible:
            box = self._checkboxes[name]
            box.blockSignals(True)
            box.setChecked(checked)
            box.blockSignals(False)
        self._update()
