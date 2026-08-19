"""« Ajouter une arme » dialog: type the weapon name only.

The category is **not** chosen here: the main window resolves the exact
category folder from the current navigation context (the folder the user is
browsing) before opening this dialog, and creates
``<catégorie courante>/<Arme>/`` on accept. The dialog itself only collects
the name — it writes nothing.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from app.i18n import t


class AddWeaponDialog(QDialog):
    """Weapon name input. ``weapon`` is read after ``exec()`` returns
    ``Accepted``. ``context_label`` is only informational (the target
    category folder, e.g. ``Skins/Primary``)."""

    def __init__(self, parent=None, context_label: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(t("add_weapon.title"))
        self.setMinimumWidth(420)

        self._context = QLabel(context_label, self)
        self._context.setObjectName("PageSubtitle")
        self._context.setWordWrap(True)

        self._weapon = QLineEdit(self)
        self._weapon.setPlaceholderText(t("add_weapon.placeholder"))
        self._weapon.textChanged.connect(self._validate)

        self._add_btn = QPushButton(t("common.add"), self)
        self._add_btn.setObjectName("PrimaryButton")
        self._add_btn.clicked.connect(self.accept)
        self._add_btn.setEnabled(False)
        cancel_btn = QPushButton(t("common.cancel"), self)
        cancel_btn.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(self._add_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(QLabel(t("add_weapon.section"), self))
        layout.addWidget(self._context)
        layout.addWidget(QLabel(t("import.weapon"), self))
        layout.addWidget(self._weapon)
        layout.addLayout(buttons)

        self._weapon.setFocus(Qt.OtherFocusReason)

    # ------------------------------------------------------------------ #
    @property
    def weapon(self) -> str:
        return self._weapon.text().strip()

    # ------------------------------------------------------------------ #
    def _validate(self, text: str) -> None:
        self._add_btn.setEnabled(bool(text.strip()))
