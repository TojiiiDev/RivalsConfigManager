"""Settings view: folders, connection test, library refresh, backups."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.backup_manager import BackupInfo
from app.config import data_dir, normalize_path
from app.i18n import available_languages, language_display_name, t
from app.themes import THEMES, theme_keys as _theme_keys

#: Shortcuts shown in the Settings section (key, i18n label). The actual
#: shortcuts are registered in the main window; this list is the single
#: display source (extensible: add a row here + a QShortcut there).
_SHORTCUT_DISPLAY = (
    ("Ctrl+F", "shortcuts.open_search"),
    ("Ctrl+H", "shortcuts.go_home"),
    ("F5", "shortcuts.verify_config"),
    ("Ctrl+Shift+Enter", "shortcuts.toggle_config"),
)


def _custom_defaults() -> dict[str, str]:
    """Default palette for the custom theme (from the dark preset)."""
    base = THEMES["dark"]
    return {
        "primary": base.accent,
        "secondary": base.border_hover,
        "accent": base.accent_hover,
        "background": base.bg,
    }


class SettingsView(QWidget):
    fleasion_changed = Signal(object)   # Path
    library_changed = Signal(object)    # Path
    test_clicked = Signal()
    refresh_clicked = Signal()
    open_fleasion_clicked = Signal()
    open_library_clicked = Signal()
    restore_clicked = Signal(object)    # BackupInfo
    backup_toggled = Signal(bool)
    hot_activation_toggled = Signal(bool)
    language_changed = Signal(str)      # language code
    theme_changed = Signal(str, dict)   # theme key, custom palette dict

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PageRoot")

        self._title = QLabel("", self)
        self._title.setObjectName("PageTitle")
        self._subtitle = QLabel("", self)
        self._subtitle.setObjectName("PageSubtitle")

        # ---- Language ---------------------------------------------------------- #
        self._language_label = QLabel("", self)
        self._language_label.setObjectName("SectionLabel")
        self._language_combo = QComboBox(self)
        for code in available_languages():
            self._language_combo.addItem(language_display_name(code), code)
        self._language_combo.currentIndexChanged.connect(self._on_language_changed)

        # ---- Fleasion folder ------------------------------------------------ #
        self._fleasion_label = QLabel("", self)
        self._fleasion_label.setObjectName("SectionLabel")
        self._fleasion_path = QLabel("—", self)
        self._fleasion_path.setObjectName("PathLabel")
        self._fleasion_path.setWordWrap(True)
        self._fleasion_browse = QPushButton("", self)
        self._fleasion_browse.clicked.connect(lambda: self._browse("fleasion"))

        # ---- Library folder ------------------------------------------------ #
        self._library_label = QLabel("", self)
        self._library_label.setObjectName("SectionLabel")
        self._library_path = QLabel("—", self)
        self._library_path.setObjectName("PathLabel")
        self._library_path.setWordWrap(True)
        self._library_browse = QPushButton("", self)
        self._library_browse.clicked.connect(lambda: self._browse("library"))

        # ---- Actions --------------------------------------------------------- #
        self._test_btn = QPushButton("", self)
        self._test_btn.clicked.connect(self.test_clicked)
        self._refresh_btn = QPushButton("", self)
        self._refresh_btn.clicked.connect(self.refresh_clicked)
        self._restore_btn = QPushButton("", self)
        self._restore_btn.clicked.connect(self._open_restore_dialog)

        self._open_fleasion_btn = QPushButton("", self)
        self._open_fleasion_btn.clicked.connect(self.open_fleasion_clicked)
        self._open_library_btn = QPushButton("", self)
        self._open_library_btn.clicked.connect(self.open_library_clicked)

        self._backup_check = QCheckBox("", self)
        self._backup_check.toggled.connect(self.backup_toggled)

        self._hot_activation_check = QCheckBox("", self)
        self._hot_activation_check.setToolTip("")
        self._hot_activation_check.toggled.connect(self.hot_activation_toggled)
        self._hot_activation_note = QLabel("", self)
        self._hot_activation_note.setStyleSheet(
            "color: #6b7280; font-size: 9pt; border: none; background: transparent;"
        )
        self._hot_activation_note.setWordWrap(True)

        # ---- Theme (1.3.0) ------------------------------------------------- #
        self._theme_label = QLabel("", self)
        self._theme_label.setObjectName("SectionLabel")
        self._theme_combo = QComboBox(self)
        for key in _theme_keys():
            self._theme_combo.addItem(t(f"theme.{key}"), key)
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)

        #: Color field labels (hot language switch).
        self._field_labels: dict[str, QLabel] = {}
        self._custom_colors: dict[str, str] = {}

        self._custom_box = QWidget(self)
        self._custom_box.setObjectName("Card")
        custom_layout = QVBoxLayout(self._custom_box)
        custom_layout.setContentsMargins(14, 10, 14, 10)
        custom_layout.setSpacing(8)
        self._custom_title = QLabel("", self._custom_box)
        self._custom_title.setObjectName("SectionLabel")
        custom_layout.addWidget(self._custom_title)
        self._custom_buttons: dict[str, QPushButton] = {}
        for field in ("primary", "secondary", "accent", "background"):
            row = QHBoxLayout()
            label = QLabel("", self._custom_box)
            label.setObjectName("CardSubtitle")
            label.setProperty("rcm_field", field)
            swatch = QPushButton("", self._custom_box)
            swatch.setFixedSize(34, 22)
            swatch.clicked.connect(lambda _=False, f=field: self._pick_color(f))
            self._custom_buttons[field] = swatch
            row.addWidget(label, 1)
            row.addWidget(swatch)
            custom_layout.addLayout(row)
            self._field_labels[field] = label
        self._gradient_check = QCheckBox("", self._custom_box)
        self._gradient_check.toggled.connect(self._on_custom_changed)
        custom_layout.addWidget(self._gradient_check)
        angle_row = QHBoxLayout()
        self._angle_label = QLabel("", self._custom_box)
        self._angle_label.setObjectName("CardSubtitle")
        self._angle_spin = QSpinBox(self._custom_box)
        self._angle_spin.setRange(0, 360)
        self._angle_spin.setValue(135)
        self._angle_spin.setSuffix("°")
        self._angle_spin.valueChanged.connect(self._on_custom_changed)
        angle_row.addWidget(self._angle_label)
        angle_row.addWidget(self._angle_spin)
        angle_row.addStretch(1)
        custom_layout.addLayout(angle_row)
        self._custom_box.hide()

        # ---- Keyboard shortcuts (1.3.0, display-only section) ----------- #
        self._shortcuts_label = QLabel("", self)
        self._shortcuts_label.setObjectName("SectionLabel")
        self._shortcuts_list = QLabel("", self)
        self._shortcuts_list.setObjectName("CardSubtitle")
        self._shortcuts_list.setWordWrap(True)

        self._info = QLabel("", self)
        self._info.setObjectName("PageSubtitle")
        self._info.setWordWrap(True)
        self._info.setStyleSheet("color: #6b7280; font-size: 9pt;")

        # Long-text widgets must never force the scroll content wider than
        # the viewport (their single-line minimumSizeHint would push the
        # language/theme selectors off-screen at small window sizes).
        for _w in (self._subtitle, self._backup_check, self._hot_activation_check,
                   self._hot_activation_note, self._fleasion_path, self._library_path,
                   self._shortcuts_list, self._info):
            self._allow_shrink(_w)

        self.retranslate()

        # ---- Layout ------------------------------------------------------------ #
        # The content is scrollable: the added sections (theme, shortcuts)
        # must never be clipped at the smallest supported window height.
        content = QWidget(self)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(40, 24, 40, 24)
        layout.setSpacing(14)
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)
        layout.addSpacing(8)

        layout.addWidget(self._language_label)
        layout.addWidget(self._language_combo)
        layout.addSpacing(10)

        layout.addWidget(self._theme_label)
        layout.addWidget(self._theme_combo)
        layout.addWidget(self._custom_box)
        layout.addSpacing(10)

        layout.addWidget(self._shortcuts_label)
        layout.addWidget(self._shortcuts_list)
        layout.addSpacing(14)

        layout.addWidget(self._fleasion_label)
        layout.addLayout(self._path_row(self._fleasion_path, self._fleasion_browse, self._open_fleasion_btn))
        layout.addSpacing(10)
        layout.addWidget(self._library_label)
        layout.addLayout(self._path_row(self._library_path, self._library_browse, self._open_library_btn))
        layout.addSpacing(16)

        actions = QHBoxLayout()
        actions.setSpacing(10)
        actions.addWidget(self._test_btn)
        actions.addWidget(self._refresh_btn)
        actions.addWidget(self._restore_btn)
        actions.addStretch(1)
        layout.addLayout(actions)
        layout.addSpacing(8)
        layout.addWidget(self._backup_check)
        layout.addSpacing(10)
        layout.addWidget(self._hot_activation_check)
        layout.addWidget(self._hot_activation_note)
        layout.addStretch(1)

        self._scroll = QScrollArea(self)
        self._scroll.setWidgetResizable(True)
        self._scroll.setWidget(content)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._scroll)
        # The info line stays OUTSIDE the scroll content: a wrapping label's
        # minimumSizeHint would otherwise force a huge minimum content width
        # and push the language/theme selectors off-screen at small sizes.
        outer.addWidget(self._info)

    @staticmethod
    def _allow_shrink(widget) -> None:
        """Let a long-text widget wrap/clip instead of forcing the scroll
        content wider than the viewport (QLabel/QCheckBox report a
        single-line minimumSizeHint even with word wrap)."""
        from PySide6.QtWidgets import QSizePolicy

        widget.setMinimumWidth(0)
        widget.setSizePolicy(QSizePolicy.Ignored, widget.sizePolicy().verticalPolicy())

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        """Apply the current language to every static text (hot switch)."""
        self._title.setText(t("settings.title"))
        self._subtitle.setText(t("settings.subtitle"))
        self._language_label.setText(t("settings.language"))
        self._theme_label.setText(t("settings.theme"))
        self._custom_title.setText(t("theme.custom_title"))
        self._gradient_check.setText(t("theme.gradient"))
        self._angle_label.setText(t("theme.gradient_angle"))
        self._shortcuts_label.setText(t("settings.shortcuts_title"))
        self._shortcuts_list.setText(
            "\n".join(
                f"{key}  —  {t(label)}"
                for key, label in _SHORTCUT_DISPLAY
            )
        )
        self._fleasion_label.setText(t("settings.fleasion_label"))
        self._library_label.setText(t("settings.library_label"))
        self._fleasion_browse.setText(t("settings.browse"))
        self._library_browse.setText(t("settings.browse"))
        self._test_btn.setText(t("settings.test"))
        self._refresh_btn.setText(t("settings.refresh"))
        self._restore_btn.setText(t("settings.restore"))
        self._open_fleasion_btn.setText(t("settings.open_folder"))
        self._open_library_btn.setText(t("settings.open_folder"))
        self._backup_check.setText(t("settings.backup_label"))
        self._hot_activation_check.setText(t("settings.hot_activation_label"))
        self._hot_activation_check.setToolTip(t("settings.hot_activation_tooltip"))
        self._hot_activation_note.setText(t("settings.hot_activation_note"))
        # Theme labels + custom field labels.
        current = self._theme_combo.currentData()
        self._theme_combo.blockSignals(True)
        self._theme_combo.clear()
        for key in _theme_keys():
            self._theme_combo.addItem(t(f"theme.{key}"), key)
        index = self._theme_combo.findData(current)
        self._theme_combo.setCurrentIndex(index if index >= 0 else 0)
        self._theme_combo.blockSignals(False)
        for field, label in self._field_labels.items():
            label.setText(t(f"theme.{field}"))

    # ------------------------------------------------------------------ #
    def _on_language_changed(self) -> None:
        """The user picked a language: emit the code — the main window
        applies it immediately (hot switch) and persists the choice."""
        code = self._language_combo.currentData()
        if code:
            self.language_changed.emit(code)

    def set_language_value(self, code: str) -> None:
        """Sync the combo with the active language (no signal loop)."""
        index = self._language_combo.findData(code)
        if index >= 0:
            self._language_combo.blockSignals(True)
            self._language_combo.setCurrentIndex(index)
            self._language_combo.blockSignals(False)

    # ------------------------------------------------------------------ #
    def set_theme_value(self, theme: str, custom: dict | None = None) -> None:
        """Sync the theme controls with the persisted settings (no signals)."""
        index = self._theme_combo.findData(theme)
        self._theme_combo.blockSignals(True)
        self._theme_combo.setCurrentIndex(index if index >= 0 else 0)
        self._theme_combo.blockSignals(False)
        self._custom_colors = dict(custom or {})
        defaults = _custom_defaults()
        for field in ("primary", "secondary", "accent", "background"):
            value = self._custom_colors.get(field) or defaults[field]
            self._custom_colors[field] = value
            self._set_swatch(field, value)
        self._gradient_check.blockSignals(True)
        self._gradient_check.setChecked(bool(self._custom_colors.get("gradient", False)))
        self._gradient_check.blockSignals(False)
        self._angle_spin.blockSignals(True)
        self._angle_spin.setValue(int(self._custom_colors.get("gradient_angle", 135)))
        self._angle_spin.blockSignals(False)
        self._custom_box.setVisible(theme == "custom")

    def _on_theme_changed(self) -> None:
        """The user picked a theme: emit the key + current custom palette."""
        key = self._theme_combo.currentData()
        if not key:
            return
        self._custom_box.setVisible(key == "custom")
        self.theme_changed.emit(key, dict(self._custom_colors))

    def _pick_color(self, field: str) -> None:
        defaults = _custom_defaults()
        current = self._custom_colors.get(field) or defaults[field]
        color = QColorDialog.getColor(QColor(current), self, t("theme.pick_color"))
        if not color.isValid():
            return
        self._custom_colors[field] = color.name()
        self._set_swatch(field, color.name())
        self._on_custom_changed()

    def _set_swatch(self, field: str, color: str) -> None:
        button = self._custom_buttons.get(field)
        if button is not None:
            button.setStyleSheet(
                f"background-color: {color}; border: 1px solid #33405c;"
                " border-radius: 6px;"
            )
            button.setToolTip(color)

    def _on_custom_changed(self) -> None:
        self._custom_colors["gradient"] = self._gradient_check.isChecked()
        self._custom_colors["gradient_angle"] = self._angle_spin.value()
        key = self._theme_combo.currentData() or "custom"
        self.theme_changed.emit(key, dict(self._custom_colors))

    # ------------------------------------------------------------------ #
    @staticmethod
    def _path_row(path_label: QLabel, browse_btn: QPushButton, open_btn: QPushButton) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(path_label, 1)
        row.addWidget(browse_btn)
        row.addWidget(open_btn)
        return row

    # ------------------------------------------------------------------ #
    def set_paths(
        self,
        fleasion: Path | None,
        library: Path | None,
        backup: bool,
        hot_activation: bool = True,
    ) -> None:
        self._fleasion_path.setText(str(fleasion) if fleasion else "—")
        self._library_path.setText(str(library) if library else "—")
        self._backup_check.blockSignals(True)
        self._backup_check.setChecked(backup)
        self._backup_check.blockSignals(False)
        self._hot_activation_check.blockSignals(True)
        self._hot_activation_check.setChecked(hot_activation)
        self._hot_activation_check.blockSignals(False)
        self._info.setText(
            t("settings.info", path=data_dir(), log_path=data_dir() / "app.log")
        )

    def _browse(self, which: str) -> None:
        current = (
            self._fleasion_path.text() if which == "fleasion" else self._library_path.text()
        )
        # The dialog must always start from a real, existing folder: a stale
        # path (e.g. a removed drive) would make the native dialog fall back
        # to the process working directory (possibly ``C:\Windows\System32``).
        start = str(Path.home())
        if current not in ("—", ""):
            candidate = Path(current)
            if candidate.is_dir():
                start = str(candidate)
        folder = QFileDialog.getExistingDirectory(self, t("common.choose_folder"), start)
        if not folder:
            return
        path = normalize_path(folder)
        if which == "fleasion":
            self._fleasion_path.setText(str(path))
            self.fleasion_changed.emit(path)
        else:
            self._library_path.setText(str(path))
            self.library_changed.emit(path)

    # ------------------------------------------------------------------ #
    def _open_restore_dialog(self, backups: list[BackupInfo] | None = None) -> None:
        from app.backup_manager import BackupManager
        from app.config import backups_dir

        manager = BackupManager(backups_dir())
        backups = backups or manager.list_backups()

        dialog = QDialog(self)
        dialog.setWindowTitle(t("settings.restore_dialog_title"))
        dialog.resize(560, 420)

        title = QLabel(t("settings.backups_available"), dialog)
        title.setObjectName("PageTitle")

        note = QLabel(t("settings.restore_note"), dialog)
        note.setObjectName("PageSubtitle")
        note.setWordWrap(True)

        list_widget = QListWidget(dialog)
        if not backups:
            empty = QListWidgetItem(t("settings.no_backups"))
            empty.setFlags(Qt.NoItemFlags)
            list_widget.addItem(empty)

        for backup in backups:
            count = backup.file_count
            suffix = "s" if count != 1 else ""
            item = QListWidgetItem(
                t("settings.backup_item", label=backup.label, count=count, s=suffix)
            )
            item.setData(Qt.UserRole, backup)
            item.setToolTip(str(backup.folder))
            list_widget.addItem(item)

        restore_btn = QPushButton(t("settings.restore_selection"), dialog)
        restore_btn.setObjectName("PrimaryButton")
        restore_btn.setEnabled(bool(backups))

        close_btn = QPushButton(t("common.close"), dialog)
        close_btn.clicked.connect(dialog.reject)

        def do_restore() -> None:
            current = list_widget.currentItem()
            if current is None:
                return
            backup = current.data(Qt.UserRole)
            dialog.accept()
            self.restore_clicked.emit(backup)

        restore_btn.clicked.connect(do_restore)

        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close_btn)
        bottom.addWidget(restore_btn)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(note)
        layout.addWidget(list_widget, 1)
        layout.addLayout(bottom)

        dialog.exec()
