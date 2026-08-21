"""Profile create/edit dialog (v1.3.0).

Fields: name, optional description, and the list of configurations the
profile captures. The list is pre-filled with the configurations currently
active in Fleasion (the user's real setup) and can be edited — the user's
choice always wins. Entries are stored as logical references (path
relative to the library root), never absolute paths.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from app.i18n import t
from app.models import ConfigItem
from app.profiles import Profile, ProfileEntry


class ProfileDialog(QDialog):
    """Create or edit a profile: name + description + configuration list.

    Two modes:

    * **manual** (default): every library configuration is listed with a
      checkbox (pre-checked when it is currently active in Fleasion) —
      the user keeps full control;
    * **capture** (v1.3.1): ``capture`` holds the configurations to save
      (e.g. the current active setup, or the mod just imported). The list
      is a read-only summary — the profile captures the current state in
      one click, no per-skin selection maze.
    """

    def __init__(
        self,
        library_root: Path | None,
        configs: list[ConfigItem],
        active_keys: set[str] | None = None,
        profile: Profile | None = None,
        capture: list[ConfigItem] | None = None,
        save_text: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._library_root = library_root
        self._configs = configs
        self._active_keys = active_keys or set()
        self._profile = profile
        self._capture = capture if capture is not None else []
        #: Libellé du bouton d'enregistrement (capture mode : « Créer le
        #: profil » ; sinon « Enregistrer »).
        self._save_text = save_text

        if self._capture:
            self.setWindowTitle(t("profiles.capture_title"))
        else:
            self.setWindowTitle(
                t("profiles.edit_title") if profile else t("profiles.create_title")
            )
        self.setMinimumSize(560, 480)

        # ---- Name ------------------------------------------------------ #
        self._name_label = QLabel(t("profiles.name"), self)
        self._name_label.setObjectName("SectionLabel")
        self._name = QLineEdit(profile.name if profile else "", self)
        self._name.setPlaceholderText(t("profiles.name_placeholder"))

        # ---- Description ----------------------------------------------- #
        self._desc_label = QLabel(t("profiles.description"), self)
        self._desc_label.setObjectName("SectionLabel")
        self._desc = QLineEdit(profile.description if profile else "", self)
        self._desc.setPlaceholderText(t("profiles.description_placeholder"))

        # ---- Configurations -------------------------------------------- #
        self._configs_label = QLabel("", self)
        self._configs_label.setObjectName("SectionLabel")

        #: « Parcourir la bibliothèque… » (v1.3.2) : build a profile through
        #: the progressive tree (Catégorie → Arme → Skin) instead of the
        #: flat list. Only available in manual mode (capture is read-only).
        self._browse_btn = QPushButton(t("profile_dialog.browse"), self)
        self._browse_btn.setObjectName("IconButton")
        self._browse_btn.setToolTip(t("profile_dialog.browse_tooltip"))
        self._browse_btn.clicked.connect(self._on_browse)
        self._browse_btn.setVisible(not self._capture)

        self._list = QListWidget(self)
        if self._capture:
            # Capture mode: read-only summary of the configurations that
            # will be saved — the profile captures the current state. No
            # checkboxes (QListWidgetItem is checkable by default; the flag
            # is explicitly removed so nothing looks selectable).
            for config in self._capture:
                item = QListWidgetItem(config.name)
                item.setData(Qt.UserRole, _relative_key(config.path, library_root))
                item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
                self._list.addItem(item)
        else:
            initial_checked = self._active_keys
            if profile is not None:
                initial_checked = {e.rel_path for e in profile.entries}
            for config in configs:
                rel = _relative_key(config.path, library_root)
                item = QListWidgetItem(config.name)
                item.setData(Qt.UserRole, rel)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(
                    Qt.Checked if rel in initial_checked else Qt.Unchecked
                )
                self._list.addItem(item)

        # ---- Buttons ---------------------------------------------------- #
        self._cancel_btn = QPushButton(t("common.cancel"), self)
        self._cancel_btn.clicked.connect(self.reject)

        self._save_btn = QPushButton("", self)
        self._save_btn.setObjectName("PrimaryButton")
        self._save_btn.clicked.connect(self._on_save)
        self._save_btn.setEnabled(False)
        self._name.textChanged.connect(self._update_buttons)

        configs_header = QHBoxLayout()
        configs_header.setSpacing(8)
        configs_header.addWidget(self._configs_label, 1)
        configs_header.addWidget(self._browse_btn)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        buttons.addWidget(self._cancel_btn)
        buttons.addWidget(self._save_btn)

        self.retranslate()
        self._update_buttons()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 18)
        layout.setSpacing(10)
        layout.addWidget(self._name_label)
        layout.addWidget(self._name)
        layout.addWidget(self._desc_label)
        layout.addWidget(self._desc)
        layout.addLayout(configs_header)
        layout.addWidget(self._list, 1)
        layout.addLayout(buttons)

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        self._save_btn.setText(self._save_text or t("common.save"))
        if self._capture:
            self._configs_label.setText(
                t("profiles.detected_note", count=len(self._capture))
            )
        else:
            self._configs_label.setText(t("profiles.capture_note"))

    # ------------------------------------------------------------------ #
    def _update_buttons(self) -> None:
        self._save_btn.setEnabled(bool(self._name.text().strip()))

    def _on_browse(self) -> None:
        """« Parcourir la bibliothèque… » (v1.3.2) : ouvre l'arbre
        progressif (Catégorie → Arme → Skin) et coche la configuration
        choisie dans la liste du profil."""
        if self._library_root is None:
            return
        from ui.views.destination_picker import DestinationPickerDialog

        dialog = DestinationPickerDialog(
            self._library_root,
            parent=self,
            pick_config=True,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        config = dialog.selected_config
        if config is None:
            return
        rel = _relative_key(config.path, self._library_root)
        # Check the item in the flat list (the user's choice wins).
        for index in range(self._list.count()):
            item = self._list.item(index)
            if item.data(Qt.UserRole) == rel:
                item.setCheckState(Qt.Checked)
                self._list.setCurrentItem(item)
                return
        # A config not listed (e.g. newly imported): append it.
        item = QListWidgetItem(config.name)
        item.setData(Qt.UserRole, rel)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setCheckState(Qt.Checked)
        self._list.addItem(item)

    def _on_save(self) -> None:
        if not self._name.text().strip():
            return
        self.accept()

    # ------------------------------------------------------------------ #
    def result_profile(self) -> Profile:
        """The profile described by the dialog (name/description/entries)."""
        entries: list[ProfileEntry] = []
        if self._capture:
            for config in self._capture:
                rel = _relative_key(config.path, self._library_root)
                entries.append(
                    ProfileEntry(
                        name=config.name,
                        rel_path=rel,
                        category=str(config.path.parent.name),
                    )
                )
        else:
            for index in range(self._list.count()):
                item = self._list.item(index)
                if item.checkState() != Qt.Checked:
                    continue
                rel = item.data(Qt.UserRole)
                name = item.text()
                config = (
                    self._configs[index]
                    if index < len(self._configs) else None
                )
                category = (
                    str(config.path.parent.name)
                    if config is not None and config.path.parent is not None
                    else Path(rel).parent.name
                )
                entries.append(
                    ProfileEntry(
                        name=name,
                        rel_path=str(rel),
                        category=category,
                    )
                )
        profile = self._profile or Profile(name="")
        profile.name = self._name.text().strip()
        profile.description = self._desc.text().strip()
        profile.entries = entries
        return profile


def _relative_key(path: Path, library_root: Path | None) -> str:
    """The logical key of a config: its path relative to the library root."""
    if library_root is not None:
        try:
            return path.relative_to(Path(library_root)).as_posix()
        except ValueError:
            pass
    return path.as_posix()
