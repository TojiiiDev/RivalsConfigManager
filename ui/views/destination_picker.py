"""Progressive tree destination picker (v1.3.1, extended in v1.3.2).

Replaces the flat « pick a category, then a weapon » experience of
« Ajouter une arme » with a step-by-step tree over the **real library
folders**:

* **Step 1 — Catégorie** : the root categories, built dynamically — the
  canonical weapon categories first (each resolved to its real on-disk
  folder, e.g. ``rivals skins/primary``), then the library's actual
  top-level folders. Nothing is hard-coded: a new folder appears
  automatically.
* **Step 2 — Arme** : the weapon folders actually present in the chosen
  category, plus « directement in <catégorie> » and (for a new weapon) an
  editable name.
* **Step 3 — Skin / configuration** (v1.3.2) : when the chosen weapon
  folder already contains configurations, they are listed here so the user
  can pick one — the destination then resolves to that config's folder
  (Category → Weapon → Skin, a real hierarchy, never a flat list).
* **Last — Confirmer** : the exact final folder, then « Créer » (or
  « Ajouter au profil » in :ref:`pick mode`).

The dialog writes nothing: the caller creates the folder (or installs the
mod) at :attr:`category_folder` / :attr:`destination`. The category is
always resolved to its real folder — a weapon is never dropped into a
brand-new root-level ``Primary`` while the real one exists elsewhere.

In **pick mode** (``pick_config=True``) the dialog is used to choose an
**existing configuration** to add to a profile: the tree is the same
(Category → Weapon → Skin), the selected config is exposed through
:attr:`selected_config` and the confirm button reads « Ajouter au profil ».
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.categories import (
    CATEGORY_KEYS,
    category_weapon_folders,
    destination_categories,
    display_label,
    folder_name_for,
    resolve_category_folder,
)
from app.i18n import t
from app.models import ConfigItem
from app.scanner import scan_library


class DestinationPickerDialog(QDialog):
    """Step-by-step tree destination picker over the real library folders.

    ``pick_config=True`` switches the dialog to profile-building mode:
    the user browses Category → Weapon → Skin and the chosen configuration
    is exposed through :attr:`selected_config` (the confirm button then
    reads « Ajouter au profil »).
    """

    def __init__(
        self,
        library_root: Path,
        parent=None,
        initial_category: str | None = None,
        pick_config: bool = False,
    ) -> None:
        super().__init__(parent)
        self._pick_config = pick_config
        self.setWindowTitle(
            t("destination.pick_title") if pick_config else t("destination.title")
        )
        self.setMinimumSize(460, 440)

        self._library_root = Path(library_root)
        self._category: str | None = None
        self._weapon: str | None = None
        self._config: ConfigItem | None = None
        #: True when the user chose « directement dans <catégorie> » (the
        #: category itself is the destination — no weapon selected).
        self._direct_in = False

        # ---- Header ---------------------------------------------------- #
        self._step_label = QLabel(t("destination.step_category"), self)
        self._step_label.setObjectName("SectionLabel")

        # ---- Pages ------------------------------------------------------ #
        self._stack = QStackedWidget(self)
        self._stack.addWidget(self._build_category_page())
        self._stack.addWidget(self._build_weapon_page())
        self._stack.addWidget(self._build_configs_page())
        self._stack.addWidget(self._build_confirm_page())

        # ---- Buttons ---------------------------------------------------- #
        self._back_btn = QPushButton(t("nav.back"), self)
        self._back_btn.clicked.connect(self._go_back)
        self._next_btn = QPushButton(t("destination.next"), self)
        self._next_btn.setObjectName("PrimaryButton")
        self._next_btn.clicked.connect(self._go_next)
        self._create_btn = QPushButton(
            t("destination.add_to_profile") if pick_config else t("destination.create"),
            self,
        )
        self._create_btn.setObjectName("PrimaryButton")
        self._create_btn.setToolTip(
            t("destination.pick_hint") if pick_config else t("destination.create_weapon_tooltip")
        )
        self._create_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton(t("common.cancel"), self)
        cancel_btn.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addWidget(self._back_btn)
        buttons.addStretch(1)
        buttons.addWidget(cancel_btn)
        buttons.addWidget(self._next_btn)
        buttons.addWidget(self._create_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(10)
        layout.addWidget(self._step_label)
        layout.addWidget(self._stack, 1)
        layout.addLayout(buttons)

        self._fill_categories(initial_category)
        self._show_step(0)

    # ------------------------------------------------------------------ #
    # Pages
    # ------------------------------------------------------------------ #
    def _build_category_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        hint = QLabel(t("destination.category_hint"), self)
        hint.setWordWrap(True)
        self._category_list = QListWidget(self)
        self._category_list.itemClicked.connect(self._on_category_clicked)
        self._category_list.itemDoubleClicked.connect(
            lambda _item: self._go_next()
        )
        layout.addWidget(hint)
        layout.addWidget(self._category_list, 1)
        return page

    def _build_weapon_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        self._weapon_hint = QLabel("", self)
        self._weapon_hint.setWordWrap(True)
        self._weapon_list = QListWidget(self)
        self._weapon_list.itemClicked.connect(self._on_weapon_clicked)
        self._weapon_list.itemDoubleClicked.connect(
            lambda _item: self._go_next()
        )
        self._new_label = QLabel(t("destination.new_weapon_label"), self)
        self._new_label.setObjectName("SectionLabel")
        self._new_weapon = QLineEdit(self)
        self._new_weapon.setPlaceholderText(t("destination.new_weapon_placeholder"))
        self._new_weapon.textChanged.connect(self._on_new_weapon_changed)
        layout.addWidget(self._weapon_hint)
        layout.addWidget(self._weapon_list, 1)
        layout.addWidget(self._new_label)
        layout.addWidget(self._new_weapon)
        return page

    def _build_configs_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        self._configs_hint = QLabel("", self)
        self._configs_hint.setWordWrap(True)
        self._configs_list = QListWidget(self)
        self._configs_list.itemClicked.connect(self._on_config_clicked)
        self._configs_list.itemDoubleClicked.connect(
            lambda _item: self._go_next()
        )
        layout.addWidget(self._configs_hint)
        layout.addWidget(self._configs_list, 1)
        return page

    def _build_confirm_page(self) -> QWidget:
        page = QWidget(self)
        layout = QVBoxLayout(page)
        hint = QLabel(
            t("destination.pick_hint") if self._pick_config else t("destination.confirm_hint"),
            self,
        )
        hint.setWordWrap(True)
        self._confirm_summary = QLabel("", self)
        self._confirm_summary.setWordWrap(True)
        self._confirm_path = QLabel("", self)
        self._confirm_path.setObjectName("PathLabel")
        self._confirm_path.setWordWrap(True)
        layout.addWidget(hint)
        layout.addWidget(self._confirm_summary)
        layout.addWidget(self._confirm_path)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------ #
    # Step 1 — categories
    # ------------------------------------------------------------------ #
    def _fill_categories(self, initial_category: str | None) -> None:
        self._category_list.clear()
        for key, folder in destination_categories(self._library_root):
            label = display_label(key)
            item = QListWidgetItem(label)
            if key in CATEGORY_KEYS and folder is None:
                item.setToolTip(
                    t(
                        "destination.will_create",
                        name=folder_name_for(key),
                    )
                )
                item.setData(
                    Qt.UserRole,
                    (key, str(self._library_root / folder_name_for(key))),
                )
            else:
                item.setData(Qt.UserRole, (key, str(folder)))
            self._category_list.addItem(item)
        # Pre-select the category the user is currently browsing, if any.
        if initial_category:
            for i in range(self._category_list.count()):
                item = self._category_list.item(i)
                if item.data(Qt.UserRole)[0] == initial_category:
                    self._category_list.setCurrentItem(item)
                    break

    # ------------------------------------------------------------------ #
    # Step 2 — weapons
    # ------------------------------------------------------------------ #
    def _on_category_clicked(self, item: QListWidgetItem) -> None:
        self._category = item.data(Qt.UserRole)[0]
        folder = Path(item.data(Qt.UserRole)[1])
        weapons = category_weapon_folders(folder) if folder.is_dir() else []

        self._weapon_list.clear()
        for name in weapons:
            w_item = QListWidgetItem(name)
            w_item.setData(Qt.UserRole, name)
            self._weapon_list.addItem(w_item)
        direct = QListWidgetItem(t("destination.directly_in", category=item.text()))
        direct.setData(Qt.UserRole, None)
        self._weapon_list.addItem(direct)
        if not weapons:
            self._weapon_hint.setText(
                t("destination.empty_category")
                + "\n"
                + t("destination.weapon_hint", category=item.text())
            )
        else:
            self._weapon_hint.setText(
                t("destination.weapon_hint", category=item.text())
            )
        self._weapon_list.setCurrentRow(0)
        self._new_weapon.clear()
        self._config = None
        self._direct_in = False

    def _on_weapon_clicked(self, item: QListWidgetItem) -> None:
        self._weapon = item.data(Qt.UserRole)
        self._direct_in = self._weapon is None  # « directement dans la catégorie »
        self._config = None

    def _on_new_weapon_changed(self, text: str) -> None:
        if text.strip():
            self._weapon = text.strip()
            self._direct_in = False
            self._config = None
            self._weapon_list.clearSelection()

    # ------------------------------------------------------------------ #
    # Step 3 — skins/configurations inside the chosen weapon (v1.3.2)
    # ------------------------------------------------------------------ #
    def _has_configs(self) -> bool:
        """True when the chosen weapon folder exists and holds configs."""
        weapon_folder = self.weapon_folder
        return weapon_folder is not None and weapon_folder.is_dir()

    def _fill_configs(self) -> None:
        """List the configurations inside the chosen weapon folder (via the
        real scanner — no second, parallel implementation)."""
        self._configs_list.clear()
        weapon_folder = self.weapon_folder
        if weapon_folder is None or not weapon_folder.is_dir():
            return
        result = scan_library(weapon_folder)
        if not result.ok or result.node is None:
            return
        for config in result.node.configs:
            item = QListWidgetItem(config.name)
            item.setData(Qt.UserRole, config)
            self._configs_list.addItem(item)

    @property
    def weapon_folder(self) -> Path | None:
        """The real folder of the chosen weapon (or ``None`` for the
        « directly in <category> » option / a brand-new weapon name)."""
        if not self._weapon:
            return None
        return self.category_folder / self._weapon

    def _on_config_clicked(self, item: QListWidgetItem) -> None:
        self._config = item.data(Qt.UserRole)

    # ------------------------------------------------------------------ #
    # Last step — confirmation
    # ------------------------------------------------------------------ #
    def _show_confirm(self) -> None:
        category = self._category or ""
        label = display_label(category)
        weapon = self._weapon
        if self._config is not None:
            self._confirm_summary.setText(f"{label} → {weapon} → {self._config.name}")
            self._confirm_path.setText(str(self._config.path))
        elif weapon:
            self._confirm_summary.setText(f"{label} → {weapon}")
            self._confirm_path.setText(str(self.destination))
        else:
            self._confirm_summary.setText(label)
            self._confirm_path.setText(str(self.destination))

    # ------------------------------------------------------------------ #
    # Navigation
    # ------------------------------------------------------------------ #
    def _show_step(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        self._step_label.setText(
            [
                t("destination.step_category"),
                t("destination.step_weapon"),
                t("destination.step_configs"),
                t("destination.step_confirm"),
            ][index]
        )
        self._back_btn.setVisible(index > 0)
        self._next_btn.setVisible(index < 2)
        self._create_btn.setVisible(index == 3)
        if index == 1:
            self._new_weapon.setFocus(Qt.OtherFocusReason)
        elif index == 2:
            self._fill_configs()
            weapon = self._weapon or ""
            self._configs_hint.setText(
                t("destination.configs_hint", weapon=weapon)
            )
            if self._configs_list.count() == 0:
                # An empty weapon folder (no skins yet): nothing to pick —
                # go straight to the confirmation page.
                self._stack.setCurrentIndex(3)
                self._step_label.setText(t("destination.step_confirm"))
                self._back_btn.setVisible(True)
                self._next_btn.setVisible(False)
                self._create_btn.setVisible(True)
                self._show_confirm()
        elif index == 3:
            self._show_confirm()

    def _go_next(self) -> None:
        current = self._stack.currentIndex()
        if current == 0:
            item = self._category_list.currentItem()
            if item is None:
                return
            self._on_category_clicked(item)
            self._show_step(1)
        elif current == 1:
            # The typed new-weapon name always wins over the list: typing
            # clears the list selection, but Qt keeps a "current item" —
            # only a *selected* item counts as choosing an existing weapon.
            typed = self._new_weapon.text().strip()
            if typed:
                self._weapon = typed
                self._direct_in = False
            else:
                current_item = self._weapon_list.currentItem()
                if current_item is not None:
                    data = current_item.data(Qt.UserRole)
                    self._weapon = data
                    self._direct_in = data is None
            if self._weapon is None and not self._direct_in:
                return
            # IMPORT : le conteneur choisi (catégorie / arme) EST la
            # destination — on n'oblige JAMAIS à sélectionner un élément
            # déjà présent. Seul le mode profil (pick_config) descend au
            # niveau des configurations.
            if self._pick_config and self._weapon and self._has_configs():
                self._show_step(2)
            else:
                self._show_step(3)
        elif current == 2:
            if self._configs_list.currentItem() is not None:
                self._config = self._configs_list.currentItem().data(Qt.UserRole)
            if self._config is None:
                return
            self._show_step(3)

    def _go_back(self) -> None:
        current = self._stack.currentIndex()
        if current == 3:
            # Retour vers l'arme (import) ou vers les configurations
            # (mode profil, si une configuration avait été choisie).
            if self._pick_config and self._config is not None:
                self._show_step(2)
            else:
                self._show_step(1)
        elif current > 0:
            self._show_step(current - 1)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt naming)
        """Entrée / validation confirme immédiatement la destination (plus
        aucune étape superflue) : avance d'une page, ou accepte sur la
        page de confirmation."""
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            if self._stack.currentIndex() == 3:
                self.accept()
            else:
                self._go_next()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------------ #
    # Result
    # ------------------------------------------------------------------ #
    @property
    def category(self) -> str | None:
        """The chosen category (canonical key or top-level folder name)."""
        return self._category

    @property
    def weapon(self) -> str | None:
        """The chosen weapon folder name (existing or new), or ``None``."""
        return self._weapon

    @property
    def selected_config(self) -> ConfigItem | None:
        """The configuration chosen in pick mode (or ``None`` otherwise)."""
        return self._config

    @property
    def category_folder(self) -> Path:
        """The real on-disk category folder (never a guessed root)."""
        if self._category in CATEGORY_KEYS:
            resolved = resolve_category_folder(self._library_root, self._category)
            if resolved is not None:
                return resolved
            return self._library_root / folder_name_for(self._category)
        return self._library_root / (self._category or "")

    @property
    def destination(self) -> Path:
        """The final folder: ``<category folder>/[<weapon>]``, or the
        chosen configuration's own folder in pick mode."""
        if self._config is not None:
            if self._config.is_folder:
                return self._config.path
            return self._config.path.parent
        dest = self.category_folder
        if self._weapon:
            dest = dest / self._weapon
        return dest
