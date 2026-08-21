"""First-launch language choice (v1.3.8, redesigned in v1.3.9).

Shown only when the user never chose a language (brand-new installation).
A modern, calm, themed screen: « Choisissez votre langue » + the 10
supported languages displayed in their **native** names (from the existing
i18n manager — no new translation system), a clear selection list and a
big primary button.

The dialog itself writes nothing: the caller (main window) persists the
choice in the existing settings.json and applies it to the whole
application *before* starting the tutorial, so the tutorial is shown in
the chosen language. The language choice is independent from the
tutorial: it is asked once, and never again.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from app.i18n import available_languages, language_display_name, t
from ui.theme import theme_color

#: Item role holding the language code.
_LANG_ROLE = Qt.UserRole


class LanguageDialog(QDialog):
    """« Choisissez votre langue » — read :attr:`selected_code` after
    ``exec()`` returns ``Accepted``."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("onboarding.language.title"))
        self.setMinimumSize(460, 540)
        self.setModal(True)

        text = theme_color("text")
        dim = theme_color("text_dim")
        accent = theme_color("accent")
        accent_hover = theme_color("accent_hover")
        accent_dark = theme_color("accent_dark")
        card = theme_color("card")
        border = theme_color("border")
        hover = theme_color("card_hover")

        self._title = QLabel(t("onboarding.language.title"), self)
        self._title.setObjectName("LanguageTitle")
        self._title.setWordWrap(True)
        self._title.setStyleSheet(
            f"font-size: 19pt; font-weight: 700; color: {text};"
            "background: transparent; border: none;"
        )

        self._body = QLabel(t("onboarding.language.body"), self)
        self._body.setObjectName("LanguageSubtitle")
        self._body.setWordWrap(True)
        self._body.setStyleSheet(
            f"font-size: 10.5pt; color: {dim};"
            "background: transparent; border: none;"
        )

        self._list = QListWidget(self)
        self._list.setObjectName("LanguageList")
        self._list.setStyleSheet(
            f"QListWidget {{ background-color: {card}; border: 1px solid {border};"
            f" border-radius: 12px; padding: 8px; outline: none; }}"
            f"QListWidget::item {{ padding: 12px 14px; font-size: 12pt;"
            f" border-radius: 8px; }}"
            f"QListWidget::item:hover {{ background-color: {hover}; }}"
            f"QListWidget::item:selected {{ background-color: {accent}; color: white; }}"
        )
        for code in available_languages():
            item = QListWidgetItem(language_display_name(code))
            item.setData(_LANG_ROLE, code)
            self._list.addItem(item)
        # Preselect the current language when there is one.
        from app.i18n import current_language

        current = current_language()
        for i in range(self._list.count()):
            if self._list.item(i).data(_LANG_ROLE) == current:
                self._list.setCurrentRow(i)
                break
        else:
            self._list.setCurrentRow(0)
        self._list.itemDoubleClicked.connect(lambda _item: self.accept())

        self._continue_btn = QPushButton(t("onboarding.continue"), self)
        self._continue_btn.setObjectName("PrimaryButton")
        self._continue_btn.setCursor(Qt.PointingHandCursor)
        self._continue_btn.setStyleSheet(
            f"QPushButton {{ background-color: {accent}; color: white; border: none;"
            f" border-radius: 12px; padding: 15px 20px; font-size: 12pt;"
            f" font-weight: 700; }}"
            f"QPushButton:hover {{ background-color: {accent_hover}; }}"
            f"QPushButton:pressed {{ background-color: {accent_dark}; }}"
        )
        self._continue_btn.clicked.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(34, 30, 34, 30)
        layout.setSpacing(14)
        layout.addWidget(self._title)
        layout.addWidget(self._body)
        layout.addSpacing(6)
        layout.addWidget(self._list, 1)
        layout.addSpacing(6)
        layout.addWidget(self._continue_btn)
        self._list.setFocus(Qt.OtherFocusReason)

    # ------------------------------------------------------------------ #
    @property
    def selected_code(self) -> str:
        """The chosen language code (defaults to the app default when the
        list is somehow empty)."""
        item = self._list.currentItem()
        if item is None:
            from app.i18n import DEFAULT_LANGUAGE

            return DEFAULT_LANGUAGE
        return str(item.data(_LANG_ROLE) or DEFAULT_LANGUAGE)  # type: ignore[arg-type]

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        """Refresh the static texts (called on a hot language switch)."""
        self.setWindowTitle(t("onboarding.language.title"))
        self._title.setText(t("onboarding.language.title"))
        self._body.setText(t("onboarding.language.body"))
        self._continue_btn.setText(t("onboarding.continue"))
