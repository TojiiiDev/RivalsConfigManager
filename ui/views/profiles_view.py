"""Profiles page (v1.3.0).

A dedicated section showing every saved profile as a card in the
application's card style: icon, name, configuration count, status, and the
actions « Appliquer », « Modifier », « Exporter » and « Supprimer ». A
toolbar offers « Créer un profil » and « Importer ».

The page is a display: the real profile logic (create/update/delete,
export/import, apply with Fleasion confirmation) lives in
:mod:`app.profiles` and is driven by the main window through signals.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.i18n import t
from app.profiles import Profile
from ui.icons import check_icon, plus_icon, users_icon, wrench_icon
from ui.theme import SUCCESS, WARNING


class ProfileCard(QFrame):
    """One profile, in the application's card style, with its actions."""

    apply_clicked = Signal(object)
    edit_clicked = Signal(object)
    delete_clicked = Signal(object)
    export_clicked = Signal(object)

    def __init__(self, profile: Profile, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._profile = profile
        self._missing = 0
        self._buttons: dict[str, QPushButton] = {}
        self._button_keys: dict[QPushButton, str] = {}

        # ---- Icon placeholder: a discreet rounded square with the first
        # letter of the profile name (no emoji, no external asset). ---- #
        icon = QLabel(profile.name[:1].upper() if profile.name else "?", self)
        icon.setAlignment(Qt.AlignCenter)
        icon.setFixedSize(44, 44)
        icon.setStyleSheet(
            "border: none; background: rgba(79, 140, 255, 0.15);"
            " border-radius: 10px; color: #9ab8ff; font-size: 16pt; font-weight: 700;"
        )

        # ---- Text block ------------------------------------------------ #
        self._name = QLabel(profile.name, self)
        self._name.setObjectName("CardTitle")
        self._desc = QLabel(profile.description or t("profiles.no_description"), self)
        self._desc.setObjectName("CardSubtitle")
        self._desc.setWordWrap(True)
        self._status = QLabel("", self)
        self._status.setObjectName("CardSubtitle")

        text = QVBoxLayout()
        text.setSpacing(3)
        text.addWidget(self._name)
        text.addWidget(self._desc)
        text.addWidget(self._status)

        # ---- Actions ---------------------------------------------------- #
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self._add_action("apply", "profiles.apply", primary=True)
        self._add_action("edit", "profiles.edit")
        self._add_action("export", "profiles.export")
        self._add_action("delete", "profiles.delete", danger=True)
        for key in ("apply", "edit", "export", "delete"):
            actions.addWidget(self._buttons[key])
        actions.addStretch(1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        layout.addWidget(icon)
        layout.addLayout(text, 1)
        layout.addLayout(actions)

        self.set_status(self._missing)

    def _add_action(self, key: str, text_key: str, primary: bool = False,
                    danger: bool = False) -> None:
        btn = QPushButton(t(text_key), self)
        btn.setProperty("rcm_action", key)
        if primary:
            btn.setObjectName("PrimaryButton")
            btn.setCursor(Qt.PointingHandCursor)
        elif danger:
            btn.setObjectName("DangerButton")
        handler = {
            "apply": self.apply_clicked,
            "edit": self.edit_clicked,
            "export": self.export_clicked,
            "delete": self.delete_clicked,
        }[key]
        btn.clicked.connect(lambda _=False, k=key: handler.emit(self._profile))
        self._buttons[key] = btn
        self._button_keys[btn] = text_key

    # ------------------------------------------------------------------ #
    def set_status(self, missing_count: int | None) -> None:
        """Statut du profil : « Prêt » (vert) ou « ⚠ N introuvable(s) »."""
        self._missing = missing_count or 0
        if self._missing:
            self._status.setText(t("profiles.status_missing", count=self._missing))
            self._status.setStyleSheet(
                f"color: {WARNING}; border: none; background: transparent;"
            )
        else:
            self._status.setText(t("profiles.status_ready"))
            self._status.setStyleSheet(
                f"color: {SUCCESS}; border: none; background: transparent;"
            )


class ProfilesView(QWidget):
    create_clicked = Signal()
    import_clicked = Signal()
    capture_clicked = Signal()          # « Enregistrer comme profil » (v1.3.1)
    import_into_clicked = Signal()      # « Importer dans un profil » (v1.3.1)
    apply_clicked = Signal(object)     # Profile
    edit_clicked = Signal(object)      # Profile
    delete_clicked = Signal(object)    # Profile
    export_clicked = Signal(object)    # Profile

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PageRoot")

        self._title = QLabel("", self)
        self._title.setObjectName("PageTitle")
        self._subtitle = QLabel("", self)
        self._subtitle.setObjectName("PageSubtitle")
        self._subtitle.setWordWrap(True)

        self._create_btn = QPushButton("", self)
        self._create_btn.setObjectName("PrimaryButton")
        self._create_btn.setCursor(Qt.PointingHandCursor)
        self._create_btn.setIcon(plus_icon())
        self._create_btn.setIconSize(QSize(16, 16))
        self._create_btn.clicked.connect(self.create_clicked)

        self._import_btn = QPushButton("", self)
        self._import_btn.setToolTip("")
        self._import_btn.setIcon(users_icon())
        self._import_btn.setIconSize(QSize(16, 16))
        self._import_btn.clicked.connect(self.import_clicked)

        self._capture_btn = QPushButton("", self)
        self._capture_btn.setIcon(check_icon())
        self._capture_btn.setIconSize(QSize(16, 16))
        self._capture_btn.clicked.connect(self.capture_clicked)

        self._import_into_btn = QPushButton("", self)
        self._import_into_btn.setIcon(wrench_icon())
        self._import_into_btn.setIconSize(QSize(16, 16))
        self._import_into_btn.clicked.connect(self.import_into_clicked)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)
        toolbar.addWidget(self._create_btn)
        toolbar.addWidget(self._capture_btn)
        toolbar.addWidget(self._import_btn)
        toolbar.addWidget(self._import_into_btn)
        toolbar.addStretch(1)

        self._cards_host = QWidget(self)
        self._cards_layout = QVBoxLayout(self._cards_host)
        self._cards_layout.setContentsMargins(0, 0, 8, 0)
        self._cards_layout.setSpacing(12)
        self._cards_layout.addStretch(1)
        self._cards: list[ProfileCard] = []

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._cards_host)

        self._empty = QLabel("", self)
        self._empty.setObjectName("PageSubtitle")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.hide()

        self.retranslate()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 24, 40, 20)
        layout.setSpacing(14)
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)
        layout.addLayout(toolbar)
        layout.addWidget(scroll, 1)
        layout.addWidget(self._empty, 1)

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        """Apply the current language to every static text (hot switch)."""
        self._title.setText(t("profiles.title"))
        self._subtitle.setText(t("profiles.subtitle"))
        self._create_btn.setText(t("profiles.create"))
        self._capture_btn.setText(t("profiles.capture"))
        self._capture_btn.setToolTip(t("profiles.capture_tooltip"))
        self._import_btn.setText(t("profiles.import"))
        self._import_btn.setToolTip(t("profiles.import_tooltip"))
        self._import_into_btn.setText(t("profiles.import_into"))
        self._import_into_btn.setToolTip(t("profiles.import_into_tooltip"))
        self._empty.setText(t("profiles.no_profiles"))
        for card in self._cards:
            card._name.setText(card._profile.name)
            card._desc.setText(card._profile.description or t("profiles.no_description"))
            for btn, text_key in card._button_keys.items():
                btn.setText(t(text_key))
            card.set_status(card._missing)

    # ------------------------------------------------------------------ #
    def set_profiles(self, profiles: list[Profile], missing: dict[str, int] | None = None) -> None:
        """Rebuild the profile cards. ``missing`` maps profile name -> count
        of configurations that are currently unresolvable."""
        missing = missing or {}
        for card in self._cards:
            card.setParent(None)
            card.deleteLater()
        self._cards = []
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for profile in profiles:
            card = ProfileCard(profile, self._cards_host)
            card.apply_clicked.connect(self.apply_clicked)
            card.edit_clicked.connect(self.edit_clicked)
            card.delete_clicked.connect(self.delete_clicked)
            card.export_clicked.connect(self.export_clicked)
            card.set_status(missing.get(profile.name, 0))
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)
            self._cards.append(card)

        self._empty.setVisible(not profiles)
        self._cards_host.setVisible(bool(profiles))
