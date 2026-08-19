"""Import popup (simple form, validated).

Explorateur → drop sur le « + » → popup :

    Catégorie → Arme → Nom du mod → Fichiers → Destination → [Installer]

The dialog is a plain form (no visual wizard, no cards, no step dots):

* **Catégorie** — combo built **dynamically** from the library's real
  folders: the canonical weapon categories first (Primaire → Secondaire →
  Mêlée → Utilitaire), then every top-level folder actually present in the
  library (Charms, Skins, Textures, custom folders, empty folders...).
  Nothing is hard-coded: a new category appears automatically. When the
  automatic detection is inconclusive the entry is forced to « — Choisir — »
  and Installer stays disabled until the user picks one: a mod is never
  installed in a guessed folder.
* **Arme** — editable combo, populated from the chosen category (library
  folders + known registry). Nothing is auto-selected when no weapon was
  detected; typing a new weapon is allowed.
* **Nom du mod** — pre-filled and freely editable. The source file is never
  renamed or modified: this name is the installed configuration's name.
* **Fichiers** — count + OBJ count + file names.
* **Destination** — exact destination, updated live.
* **Doublons** — detected (name/file/hash) with an explicit choice:
  « Garder les deux » or « Remplacer » (the existing mod is backed up).

Nothing is written before « Installer ». All the import protections (anti
zip-slip, duplicates, backup before replace, validation, staging cleanup)
live in ``app.mod_import`` and are unchanged.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)

from app.categories import display_label, import_categories
from app.detection import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    detect,
    detect_source_dependencies,
    suggest_name,
    weapons_for_category,
)
from app.i18n import t
from app.models import Node
from app.mod_import import (
    MODE_KEEP_BOTH,
    MODE_REPLACE,
    InstallPlan,
    ModAnalysis,
    build_plan,
)


class ImportDialog(QDialog):
    """Simple import form: category → weapon → name → files → destination."""

    def __init__(
        self,
        analysis: ModAnalysis,
        library_root: Path,
        parent=None,
        library_node: Node | None = None,
    ) -> None:
        super().__init__(parent)
        # ``library_node`` is kept for API compatibility (weapon images used
        # by the visual wizard); the simple form does not need it.
        del library_node
        self.setWindowTitle(t("import.title"))
        self.setMinimumSize(560, 480)
        self._analysis = analysis
        self._library_root = library_root
        self._plan: InstallPlan | None = None

        # ---- Fields (in the validated order) --------------------------- #
        self._category = QComboBox(self)
        # Built dynamically from the library's real top-level folders
        # (canonical weapon categories first, then the actual folders —
        # Charms, Skins, Textures, custom folders, empty folders...).
        # Nothing is hard-coded: a new category folder appears here
        # automatically, without touching the code.
        for key in import_categories(self._library_root):
            self._category.addItem(display_label(key), key)
        self._category.currentIndexChanged.connect(self._on_category_changed)

        self._weapon = QComboBox(self)
        self._weapon.setEditable(True)
        self._weapon.setInsertPolicy(QComboBox.NoInsert)
        self._weapon.setPlaceholderText(t("import.weapon_placeholder"))
        self._weapon.currentTextChanged.connect(self._update)

        # ---- Progressive tree destination picker (v1.3.1) -------------- #
        # The flat form stays the reference; this button opens the tree
        # over the REAL library folders (categories → weapons → confirm)
        # and pre-fills the two combos on accept. The final decision always
        # remains editable below.
        self._pick_dest_btn = QPushButton("", self)
        self._pick_dest_btn.setObjectName("PrimaryButton")
        self._pick_dest_btn.clicked.connect(self._pick_destination)

        self._name = QLineEdit(suggest_name(analysis.name), self)
        self._name.setPlaceholderText(t("import.name_placeholder"))
        self._name.textChanged.connect(self._update)

        self._files_label = QLabel("", self)
        self._files_label.setWordWrap(True)

        self._detect_label = QLabel("", self)
        self._detect_label.setWordWrap(True)

        self._dest_label = QLabel("", self)
        self._dest_label.setObjectName("PathLabel")
        self._dest_label.setWordWrap(True)

        # ---- Duplicates ------------------------------------------------ #
        self._dup_label = QLabel("", self)
        self._dup_label.setWordWrap(True)
        self._dup_label.setStyleSheet(
            "color: #fbbf24; border: 1px solid #fbbf24; border-radius: 8px;"
            " padding: 6px; background: rgba(251, 191, 36, 0.08);"
        )
        self._dup_label.hide()

        self._keep_both = QRadioButton("", self)
        self._replace = QRadioButton("", self)
        self._keep_both.setChecked(True)
        self._keep_both.toggled.connect(self._update)
        self._replace.toggled.connect(self._update)

        # ---- Buttons ---------------------------------------------------- #
        self._cancel_btn = QPushButton(t("common.cancel"), self)
        self._cancel_btn.clicked.connect(self.reject)

        self._install_btn = QPushButton("", self)
        self._install_btn.setObjectName("PrimaryButton")
        self._install_btn.clicked.connect(self.accept)
        self._install_btn.setEnabled(False)
        self._install_btn.setText(t("import.install"))

        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addStretch(1)
        buttons.addWidget(self._cancel_btn)
        buttons.addWidget(self._install_btn)

        # ---- Layout (validated order) ----------------------------------- #
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel(t("import.section_title"), self))
        title_row.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 20, 28, 18)
        layout.setSpacing(10)
        layout.addLayout(title_row)
        layout.addWidget(self._detect_label)
        layout.addWidget(QLabel(t("import.category"), self))
        layout.addWidget(self._category)
        layout.addWidget(self._pick_dest_btn)
        layout.addWidget(QLabel(t("import.weapon"), self))
        layout.addWidget(self._weapon)
        layout.addWidget(QLabel(t("import.name"), self))
        layout.addWidget(self._name)
        layout.addWidget(QLabel(t("import.files"), self))
        layout.addWidget(self._files_label)
        layout.addWidget(QLabel(t("import.destination"), self))
        layout.addWidget(self._dest_label)
        layout.addWidget(self._dup_label)
        layout.addWidget(self._keep_both)
        layout.addWidget(self._replace)
        layout.addStretch(1)
        layout.addLayout(buttons)

        self._keep_both.setText(t("import.keep_both"))
        self._replace.setText(t("import.replace"))
        self._pick_dest_btn.setText(t("import.pick_destination"))
        self._pick_dest_btn.setToolTip(t("import.pick_destination_tooltip"))

        # ---- Detection: pre-fills only, never imposes a destination ---- #
        self._detection = detect(analysis.name, library_root)
        self._source_deps = detect_source_dependencies(analysis)
        self._apply_detection()
        self._update()

    # ------------------------------------------------------------------ #
    # Detection prefill + plan
    # ------------------------------------------------------------------ #
    def _apply_detection(self) -> None:
        det = self._detection
        if det.category:
            index = self._category.findData(det.category)
            if index >= 0:
                self._category.setCurrentIndex(index)  # -> _on_category_changed
        else:
            self._category.insertItem(0, t("import.choose"), None)
            self._category.setCurrentIndex(0)

        # Peuplement garanti même quand l'index de catégorie n'a pas bougé
        # (ex. détection = Primaire, déjà sélectionné : pas de signal).
        self._reload_weapons()

        if det.weapon:
            self._weapon.setCurrentText(det.weapon)  # pré-remplissage après peuplement
        else:
            self._update()

        lines = []
        if det.confidence == CONFIDENCE_HIGH:
            lines.append(t("import.detected_high", label=det.label, source=det.source))
        elif det.confidence == CONFIDENCE_MEDIUM:
            lines.append(t("import.detected_medium", label=det.label))
        else:
            lines.append(t("import.detected_low"))
        # Dépendances détectées dans le contenu (OBJ / MP3) — information
        # seule ; la décision finale (catégorie, arme) reste à l'utilisateur.
        if self._source_deps.any:
            lines.append(t("detection.deps_label", deps=self._source_deps.label))
        self._detect_label.setText("\n".join(lines))
        if det.confidence == CONFIDENCE_HIGH:
            self._detect_label.setStyleSheet(
                "color: #7ee787; border: none; background: transparent;"
            )
        else:
            self._detect_label.setStyleSheet(
                "color: #fbbf24; border: none; background: transparent;"
            )

    def _reload_weapons(self) -> None:
        """Repopulate the weapon picker for the selected category.

        Nothing is auto-selected: a mod without a detected weapon must stay
        at category level (weapon facultatif), never silently attached to
        the first weapon of the list.
        """
        category = self._category.currentData()
        self._weapon.blockSignals(True)
        try:
            self._weapon.clear()
            if category:
                self._weapon.addItems(
                    weapons_for_category(self._library_root, category)
                )
            self._weapon.setCurrentIndex(-1)
            self._weapon.setEditText("")
        finally:
            self._weapon.blockSignals(False)

    def _on_category_changed(self) -> None:
        self._reload_weapons()
        self._update()

    # ------------------------------------------------------------------ #
    def _pick_destination(self) -> None:
        """Open the progressive tree over the real library folders and
        apply the chosen category + weapon to the flat form."""
        from ui.views.destination_picker import DestinationPickerDialog

        initial = self._category.currentData()
        dialog = DestinationPickerDialog(
            self._library_root,
            parent=self,
            initial_category=initial if isinstance(initial, str) else None,
        )
        if dialog.exec() != QDialog.Accepted:
            return
        category = dialog.category
        weapon = dialog.weapon
        if category:
            index = self._category.findData(category)
            if index >= 0:
                self._category.setCurrentIndex(index)  # -> _on_category_changed
            else:
                self._category.addItem(display_label(category), category)
                self._category.setCurrentIndex(self._category.count() - 1)
        if weapon:
            self._weapon.setEditText(weapon)
        self._update()

    # ------------------------------------------------------------------ #
    def _update(self) -> None:
        category = self._category.currentData()
        if category is None:
            self._plan = None
            self._install_btn.setEnabled(False)
            self._dest_label.setText(t("import.choose_category"))
            self._dup_label.hide()
            self._keep_both.setVisible(False)
            self._replace.setVisible(False)
            return

        self._plan = build_plan(
            self._name.text(),
            category,
            self._weapon.currentText(),
            self._analysis,
            self._library_root,
            mode=MODE_REPLACE if self._replace.isChecked() else MODE_KEEP_BOTH,
        )
        self._install_btn.setEnabled(True)
        self._dest_label.setText(str(self._plan.destination))

        # Files summary: count + OBJ + names.
        n_files = len(self._analysis.files)
        bits = [f"{n_files} " + (t("unit.file_one") if n_files == 1 else t("unit.file_many"))]
        if self._analysis.obj_count:
            bits.append(t("import.obj_count", count=self._analysis.obj_count))
        names = " · ".join(f.rel for f in self._analysis.files[:8])
        if len(self._analysis.files) > 8:
            names += f" · {t('import.more_files', count=len(self._analysis.files) - 8)}"
        self._files_label.setText(" · ".join(bits) + ("\n" + names if names else ""))

        dups = self._plan.duplicates
        if dups:
            lines = "\n".join(f"• {d.details}" for d in dups[:6])
            more = (
                f"\n{t('import.duplicates_more', count=len(dups) - 6)}"
                if len(dups) > 6
                else ""
            )
            self._dup_label.setText(
                t("import.duplicates", lines=lines) + more
            )
            self._dup_label.show()
            self._keep_both.setVisible(True)
            self._replace.setVisible(True)
        else:
            self._dup_label.hide()
            self._keep_both.setVisible(False)
            self._replace.setVisible(False)

    # ------------------------------------------------------------------ #
    def build_plan(self) -> InstallPlan:
        """The current plan (recomputed with the chosen duplicate mode)."""
        assert self._plan is not None
        mode = MODE_REPLACE if self._replace.isChecked() else MODE_KEEP_BOTH
        self._plan = build_plan(
            self._name.text(),
            self._category.currentData(),
            self._weapon.currentText(),
            self._analysis,
            self._library_root,
            mode=mode,
        )
        return self._plan

    @property
    def plan(self) -> InstallPlan | None:
        return self._plan
