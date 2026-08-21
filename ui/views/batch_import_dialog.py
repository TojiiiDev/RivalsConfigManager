"""Batch import dialog (v1.3.12) — « Importer plusieurs éléments ».

After the sources have been analysed (:mod:`app.batch_import`), this
dialog presents every detected element as an individual row and lets the
user sort each one **independently** before validating the whole batch
once.

The destination is a true **cascade selector**:

* ``[ Catégorie ▼ ]`` — real categories only (canonical weapon categories
  + the library's actual top-level folders; nothing hard-coded, no
  phantom category);
* ``[ → Destination ▼ ]`` — **dependent on the category of that row only**
  and populated from the real structure of the chosen category (its
  sub-folders, empty ones included). It is a pure list (never editable):
  no text field to fill, no pre-filled name — you choose from the list.
  It is disabled until a category is chosen and is never pre-filled with
  a generic destination;
* a category that has no sub-level (Utility, Charms...) is directly a
  final destination: the second box is disabled with a clear message
  (« Aucun sous-niveau — la catégorie est la destination ») and the
  category alone completes the row;
* for a category containing weapons, the weapon must be chosen **in the
  list**; creating a new destination is an explicit, separate action
  (« + Nouvelle destination »), never an automatic text field;
* a detected weapon is pre-selected only when it really exists in the
  list — never invented from a detected name;
* changing one row never affects the others;
* the footer shows the count and the single [ Importer les n ] button —
  the list itself is the recap, no per-element confirmation at install.

Nothing is written before the final validation; the install then goes
through the unchanged ``app.mod_import`` pipeline.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from app.batch_import import BatchItem
from app.categories import (
    CATEGORY_KEYS,
    category_weapon_folders,
    display_label,
    folder_name_for,
    import_categories,
    resolve_category_folder,
    safe_folder_name,
)
from app.detection import CONFIDENCE_LOW
from app.i18n import t


class _Row(QFrame):
    """One importable element: name + detection + its own destination."""

    changed = Signal()

    def __init__(self, item: BatchItem, library_root, parent=None) -> None:
        super().__init__(parent)
        self._item = item
        self._library_root = library_root
        self._has_subs = False  # la catégorie choisie a-t-elle des sous-destinations ?

        self._name = QLabel(item.name, self)
        self._name.setObjectName("OnboardingBubbleTitle")
        self._name.setWordWrap(True)
        if item.origin and item.origin != item.name:
            source_hint = f"  ·  {item.origin}"
            self._name.setText(f"{item.name}{source_hint}")
        self._name.setStyleSheet(
            f"font-size: 11pt; font-weight: 700; color: {self._text_color()};"
            "background: transparent; border: none;"
        )

        self._status = QLabel("", self)
        self._status.setWordWrap(True)
        self._status.setStyleSheet("background: transparent; border: none;")

        # ---- Destination (independent per row) ------------------------- #
        self._category = QComboBox(self)
        self._category.setMinimumWidth(190)
        for key in import_categories(self._library_root):
            self._category.addItem(display_label(key), key)
        self._category.currentIndexChanged.connect(self._on_category_changed)

        # ---- Sélecteur en cascade : → Destination ▼ -------------------- #
        # La case suivante est une VRAIE liste, non éditable : elle liste
        # les destinations RÉELLEMENT disponibles dans la catégorie choisie
        # (ses sous-dossiers, même vides). Aucun champ texte à remplir,
        # aucun nom prérempli : on choisit dans la liste. Un dossier sans
        # sous-niveau (Utility, Charms...) est directement une destination
        # finale : un message clair l'indique. La création d'une nouvelle
        # destination est une action EXPLICITE et séparée (« + Nouvelle
        # destination »), jamais un champ de saisie automatique.
        self._arrow = QLabel("→", self)
        self._arrow.setStyleSheet(
            f"color: {self._dim_color()}; background: transparent; border: none;"
            " font-size: 12pt;"
        )
        self._arrow.setAlignment(Qt.AlignCenter)

        self._weapon = QComboBox(self)
        self._weapon.setPlaceholderText(t("batch_import.choose_destination"))
        self._weapon.setMinimumWidth(170)
        self._weapon.setEnabled(False)
        self._weapon.setToolTip(t("batch_import.destination_tooltip"))
        self._weapon.currentIndexChanged.connect(self._on_weapon_changed)

        self._new_btn = QPushButton(t("batch_import.new_destination"), self)
        self._new_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {self._accent_color()};"
            f" border: 1px solid {self._accent_color()}55; border-radius: 8px;"
            " padding: 4px 10px; font-size: 9pt; }"
            f"QPushButton:hover {{ background: {self._accent_color()}1a; }}"
        )
        self._new_btn.setCursor(Qt.PointingHandCursor)
        self._new_btn.setToolTip(t("batch_import.new_destination_tooltip"))
        self._new_btn.clicked.connect(self._on_new_destination)
        self._new_btn.setVisible(False)

        combo_row = QHBoxLayout()
        combo_row.setContentsMargins(0, 0, 0, 0)
        combo_row.setSpacing(10)
        combo_row.addWidget(self._category)
        combo_row.addWidget(self._arrow, 0)
        combo_row.addWidget(self._weapon, 1)
        combo_row.addWidget(self._new_btn, 0)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(6)
        layout.addWidget(self._name)
        layout.addLayout(combo_row)
        layout.addWidget(self._status)

        self._apply_detection()

    # ------------------------------------------------------------------ #
    @staticmethod
    def _text_color() -> str:
        try:
            from ui.theme import theme_color

            return theme_color("text")
        except Exception:  # pragma: no cover - défensif
            return "#e8ebf2"

    @staticmethod
    def _dim_color() -> str:
        try:
            from ui.theme import theme_color

            return theme_color("text_dim")
        except Exception:  # pragma: no cover - défensif
            return "#8b93a7"

    @staticmethod
    def _accent_color() -> str:
        try:
            from ui.theme import theme_color

            return theme_color("accent")
        except Exception:  # pragma: no cover - défensif
            return "#4f8cff"

    def _apply_detection(self) -> None:
        """Pre-select the detected destination when the evidence is solid;
        otherwise force « — Choisir — » (never an invented category)."""
        item = self._item
        if item.detected_category is not None and item.confidence != CONFIDENCE_LOW:
            index = self._category.findData(item.detected_category)
            if index >= 0:
                self._category.setCurrentIndex(index)
            else:
                # Catégorie détectée mais absente de la bibliothèque : on
                # la garde quand même dans la liste (canonique) si c'en est
                # une, sinon destination à choisir.
                if item.detected_category in CATEGORY_KEYS:
                    self._category.addItem(display_label(item.detected_category),
                                           item.detected_category)
                    self._category.setCurrentIndex(self._category.count() - 1)
                else:
                    self._force_choose()
        else:
            self._force_choose()
        # La cascade est peuplée EXPLICITEMENT : elle ne dépend pas du signal
        # ``currentIndexChanged``, qui ne se déclenche pas quand la catégorie
        # détectée est déjà l'index courant (ex. « primary », premier élément
        # de la liste) — sans cela la case Destination resterait vide et une
        # arme détectée serait perdue à l'installation.
        self._on_category_changed()
        if item.weapon:
            self._weapon.setCurrentText(item.weapon)
        self._refresh_status()

    def _force_choose(self) -> None:
        """Aucune catégorie fiable : l'entrée « Choisir une catégorie » est
        sélectionnée — jamais une catégorie inventée."""
        if self._category.findData(None) < 0:
            self._category.insertItem(0, t("batch_import.choose_category"), None)
        self._category.setCurrentIndex(self._category.findData(None))

    def _category_folder(self, category: str):
        """Le dossier RÉEL de la catégorie (canonique résolue dans la
        bibliothèque — jamais un « Primary » inventé à la racine)."""
        if category in CATEGORY_KEYS:
            resolved = resolve_category_folder(self._library_root, category)
            if resolved is not None:
                return resolved
            return self._library_root / folder_name_for(category)
        return self._library_root / category

    def _on_category_changed(self) -> None:
        """Cascade : la case Destination est remplacée par les destinations
        RÉELLES de la catégorie choisie sur CETTE ligne uniquement (ses
        sous-dossiers, même vides). Aucune destination générique n'est
        jamais pré-affichée, aucun nom n'est prérempli dans un champ texte.

        * catégorie sans sous-niveau → la catégorie est la destination
          finale : message clair, case désactivée, jamais une saisie ;
        * catégorie avec armes → case activée, UNIQUEMENT ces armes ;
        * arme détectée → pré-sélectionnée seulement si elle existe
          réellement dans la liste (jamais inventée depuis le nom détecté).
        """
        category = self._category.currentData()
        detected = getattr(self._item, "detected_weapon", None)
        self._weapon.blockSignals(True)
        try:
            self._weapon.clear()
            if category:
                folder = self._category_folder(category)
                subs = (
                    category_weapon_folders(folder)
                    if folder.is_dir()
                    else []
                )
                self._has_subs = bool(subs)
                for name in subs:
                    self._weapon.addItem(name, name)
                if self._has_subs:
                    self._weapon.setEnabled(True)
                    self._weapon.setPlaceholderText(t("batch_import.choose_weapon"))
                    self._weapon.setCurrentIndex(-1)
                    if detected and detected in subs:
                        self._weapon.setCurrentText(detected)
                    self._new_btn.setVisible(True)
                else:
                    # Pas de sous-niveau : la catégorie est directement la
                    # destination finale — message explicite, jamais un
                    # champ vide ou une saisie à compléter.
                    self._weapon.setEnabled(False)
                    self._weapon.setPlaceholderText(t("batch_import.no_sublevel"))
                    self._new_btn.setVisible(False)
            else:
                self._has_subs = False
                self._weapon.setEnabled(False)
                self._weapon.setPlaceholderText(t("batch_import.choose_destination"))
                self._new_btn.setVisible(False)
        finally:
            self._weapon.blockSignals(False)
        self._refresh_status()
        self.changed.emit()

    def _on_weapon_changed(self) -> None:
        """Une arme choisie DANS la liste termine la ligne : le statut et le
        bouton d'import sont actualisés immédiatement (aucune étape
        superflue, aucun signal manquant qui bloquerait la validation)."""
        self._refresh_status()
        self.changed.emit()

    def _create_destination(self, name: str) -> None:
        """Création EXPLICITE d'une nouvelle destination pour CETTE ligne
        (bouton « + Nouvelle destination »). Le nom est ajouté à la liste
        puis sélectionné ; un nom déjà présent est simplement sélectionné.
        La création n'a jamais lieu automatiquement (aucune destination
        inventée depuis un nom détecté)."""
        clean = safe_folder_name(name)
        if not clean or not self._has_subs:
            return
        index = -1
        for i in range(self._weapon.count()):
            if self._weapon.itemText(i).casefold() == clean.casefold():
                index = i
                break
        if index >= 0:
            self._weapon.setCurrentIndex(index)
        else:
            self._weapon.addItem(clean, clean)
            self._weapon.setCurrentIndex(self._weapon.count() - 1)
        self._refresh_status()
        self.changed.emit()

    def _on_new_destination(self) -> None:
        """Bouton « + Nouvelle destination » : demande le nom, puis crée la
        destination (action volontaire et séparée — jamais automatique)."""
        name, ok = QInputDialog.getText(
            self,
            t("batch_import.new_destination_title"),
            t("batch_import.new_destination_prompt"),
        )
        if ok and name.strip():
            self._create_destination(name.strip())

    def _row_complete(self) -> bool:
        """Une ligne est terminée quand sa destination réelle est connue :

        * catégorie avec armes → une arme doit être choisie DANS la liste ;
        * catégorie sans sous-niveau → la catégorie seule suffit.
        """
        category = self._category.currentData()
        if category is None:
            return False
        if not self._has_subs:
            return True
        return (
            self._weapon.currentIndex() >= 0
            and self._weapon.currentData() is not None
        )

    def _refresh_status(self) -> None:
        item = self._item
        if not self._row_complete():
            self._status.setText(t("batch_import.to_choose"))
            self._status.setStyleSheet(
                "color: #fbbf24; background: transparent; border: none;"
            )
        elif item.confidence != CONFIDENCE_LOW:
            self._status.setText(t("batch_import.detected", label=item.detected_label))
            self._status.setStyleSheet(
                "color: #7ee787; background: transparent; border: none;"
            )
        else:
            self._status.setText(t("batch_import.manual"))
            self._status.setStyleSheet(
                "color: #8b93a7; background: transparent; border: none;"
            )

    # ------------------------------------------------------------------ #
    def apply_choices(self) -> None:
        """Write the chosen destination back on the item (single source of
        truth for the install step).

        * sous-dossier choisi (ou créé explicitement) → son nom d'arme ;
        * catégorie sans sous-niveau → ``None`` (la catégorie est la
          destination finale).
        """
        item = self._item
        item.category = self._category.currentData()
        if item.category is None or not self._has_subs:
            item.weapon = None
            return
        item.weapon = self._weapon.currentData()


class BatchImportDialog(QDialog):
    """« Importer plusieurs éléments » — sort each element, validate once."""

    def __init__(self, items: list[BatchItem], library_root, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(t("batch_import.title"))
        self.setMinimumSize(720, 520)
        self._items = list(items)
        self._library_root = library_root
        self._rows: list[_Row] = []

        # ---- Header ----------------------------------------------------- #
        n = len(items)
        self._count_label = QLabel(
            t("batch_import.count", count=n, s="" if n == 1 else "s"), self
        )
        self._count_label.setObjectName("PageSubtitle")
        # En-tête des colonnes : Catégorie → Destination (cascade).
        self._columns_header = QLabel(
            f"{t('import.category')}   →   {t('import.destination')}", self
        )
        self._columns_header.setObjectName("SectionLabel")

        # ---- Rows ------------------------------------------------------- #
        rows_host = QWidget(self)
        rows_layout = QVBoxLayout(rows_host)
        rows_layout.setContentsMargins(0, 0, 8, 0)
        rows_layout.setSpacing(10)
        for item in items:
            row = _Row(item, library_root, rows_host)
            row.changed.connect(self._on_row_changed)
            rows_layout.addWidget(row)
            self._rows.append(row)
        rows_layout.addStretch(1)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setWidget(rows_host)

        # ---- Footer ----------------------------------------------------- #
        self._cancel_btn = QPushButton(t("common.cancel"), self)
        self._cancel_btn.clicked.connect(self.reject)

        self._import_btn = QPushButton(
            t("batch_import.import_button", count=n, s="" if n == 1 else "s"), self
        )
        self._import_btn.setObjectName("PrimaryButton")
        self._import_btn.setEnabled(False)
        self._import_btn.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        buttons.addWidget(self._cancel_btn)
        buttons.addWidget(self._import_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 18)
        layout.setSpacing(12)
        layout.addWidget(self._count_label)
        layout.addWidget(self._columns_header)
        layout.addWidget(scroll, 1)
        layout.addLayout(buttons)

        self._on_row_changed()

    # ------------------------------------------------------------------ #
    def _on_row_changed(self) -> None:
        """The batch can only be imported once EVERY element has a real
        destination (never a silent partial install)."""
        self._import_btn.setEnabled(
            all(row._row_complete() for row in self._rows)
        )

    def result_items(self) -> list[BatchItem]:
        """The items with the user's final destinations applied."""
        for row in self._rows:
            row.apply_choices()
        return self._items
