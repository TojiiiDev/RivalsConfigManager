"""First-run welcome view: choose the two folders."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from app.config import normalize_path
from app.i18n import t


class WelcomeView(QWidget):
    continue_clicked = Signal(object, object)  # (fleasion_dir, library_dir)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PageRoot")

        self._title = QLabel("", self)
        self._title.setObjectName("AppTitle")
        self._title.setWordWrap(True)

        self._subtitle = QLabel("", self)
        self._subtitle.setObjectName("AppSubtitle")
        self._subtitle.setWordWrap(True)

        self._fleasion_label = QLabel("", self)
        self._fleasion_label.setObjectName("SectionLabel")
        self._fleasion_path = QLabel("—", self)
        self._fleasion_path.setObjectName("PathLabel")
        self._fleasion_path.setWordWrap(True)
        self._fleasion_select = QPushButton("", self)
        self._fleasion_select.clicked.connect(lambda: self._pick("fleasion"))

        self._library_label = QLabel("", self)
        self._library_label.setObjectName("SectionLabel")
        self._library_path = QLabel("—", self)
        self._library_path.setObjectName("PathLabel")
        self._library_path.setWordWrap(True)
        self._library_select = QPushButton("", self)
        self._library_select.clicked.connect(lambda: self._pick("library"))

        self._continue_btn = QPushButton("", self)
        self._continue_btn.setObjectName("PrimaryButton")
        self._continue_btn.setMinimumHeight(48)
        self._continue_btn.setEnabled(False)
        self._continue_btn.clicked.connect(self._continue)

        self._fleasion_dir: Path | None = None
        self._library_dir: Path | None = None

        self.retranslate()

        # Layout ------------------------------------------------------------- #
        card = QWidget(self)
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(12)
        card_layout.addWidget(self._fleasion_label)
        card_layout.addLayout(self._row(self._fleasion_path, self._fleasion_select))
        card_layout.addSpacing(8)
        card_layout.addWidget(self._library_label)
        card_layout.addLayout(self._row(self._library_path, self._library_select))
        card_layout.addSpacing(20)
        card_layout.addWidget(self._continue_btn, 0, Qt.AlignRight)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(60, 60, 60, 60)
        layout.setSpacing(12)
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)
        layout.addSpacing(16)
        layout.addWidget(card)
        layout.addStretch(1)

    # ------------------------------------------------------------------ #
    @staticmethod
    def _row(path_label: QLabel, button: QPushButton) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(path_label, 1)
        row.addWidget(button)
        return row

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        """Apply the current language to every static text (hot switch)."""
        self._title.setText(t("welcome.title"))
        self._subtitle.setText(t("welcome.subtitle"))
        self._fleasion_label.setText(t("welcome.fleasion_label"))
        self._library_label.setText(t("welcome.library_label"))
        self._fleasion_select.setText(t("welcome.select"))
        self._library_select.setText(t("welcome.select"))
        self._continue_btn.setText(t("welcome.continue"))

    # ------------------------------------------------------------------ #
    def _pick(self, which: str) -> None:
        current = self._fleasion_dir if which == "fleasion" else self._library_dir
        # Only use the previous path as the dialog start when it still
        # exists; otherwise fall back to the user's home folder so the
        # native dialog never opens on the process working directory.
        start = str(Path.home())
        if current is not None and current.is_dir():
            start = str(current)
        folder = QFileDialog.getExistingDirectory(self, t("common.choose_folder"), start)
        if not folder:
            return
        path = normalize_path(folder)
        if which == "fleasion":
            self._fleasion_dir = path
            self._fleasion_path.setText(str(path))
        else:
            self._library_dir = path
            self._library_path.setText(str(path))
        self._continue_btn.setEnabled(bool(self._fleasion_dir and self._library_dir))

    def _continue(self) -> None:
        if self._fleasion_dir and self._library_dir:
            self.continue_clicked.emit(self._fleasion_dir, self._library_dir)
