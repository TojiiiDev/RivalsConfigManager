"""Configuration detail view with preview, OBJ management and ACTIVATE.

The ACTIVATE button reflects the real state of the configuration in
Fleasion:

* ``ACTIVER`` — not present in Fleasion yet;
* ``✓ COPIÉ`` — files were copied but Fleasion selection could not be
  confirmed (manual selection required);
* ``✓ ACTIF`` — Fleasion selection was confirmed (via settings.json).
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

from app.config_analysis import analyze_item
from app.fleasion import ActivationOutcome, DeactivateOutcome
from app.i18n import t
from app.models import ConfigItem
from app.sync import ISSUE_STALE_COPY, ISSUE_UNMANAGED, SyncReport
from app.verify import ConfigVerification
from ui.icons import check_icon, wrench_icon
from ui.theme import DANGER, SUCCESS, WARNING, theme_color
from ui.widgets.preview import PreviewLabel

STATE_INACTIVE = "inactive"
STATE_COPIED = "copied"
STATE_ACTIVE = "active"


class ConfigView(QWidget):
    activate_clicked = Signal()
    deactivate_clicked = Signal()
    delete_clicked = Signal()
    open_source_clicked = Signal()
    edit_image_clicked = Signal()
    add_obj_clicked = Signal()
    remove_obj_clicked = Signal()
    verify_clicked = Signal()   # « Vérifier » (v1.3.0)
    repair_clicked = Signal()   # « Réparer » (v1.3.0, only when relevant)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("PageRoot")

        self._preview = PreviewLabel(360, self)

        self._name = QLabel("", self)
        self._name.setObjectName("PageTitle")
        self._name.setWordWrap(True)

        self._path = QLabel("", self)
        self._path.setObjectName("PathLabel")
        self._path.setWordWrap(True)

        self._files_label = QLabel("", self)
        self._files_label.setObjectName("SectionLabel")

        # ---- Dépendances (OBJ) : petite zone discrète sous les fichiers. --- #
        self._deps_label = QLabel("", self)
        self._deps_label.setObjectName("SectionLabel")
        self._deps_content = QLabel("", self)
        self._deps_content.setWordWrap(True)
        self._deps_content.setTextFormat(Qt.RichText)
        self._deps_content.setStyleSheet(
            "border: none; background: transparent; font-size: 9.5pt;"
        )
        self._deps_box = QFrame(self)
        self._deps_box.setObjectName("Card")
        deps_box_layout = QVBoxLayout(self._deps_box)
        deps_box_layout.setContentsMargins(14, 10, 14, 10)
        deps_box_layout.setSpacing(6)
        deps_box_layout.addWidget(self._deps_label)
        deps_box_layout.addWidget(self._deps_content)
        self._deps_box.hide()

        files_scroll = QScrollArea(self)
        files_scroll.setWidgetResizable(True)
        files_scroll.setFixedHeight(150)
        self._files_list = QWidget(files_scroll)
        self._files_layout = QVBoxLayout(self._files_list)
        self._files_layout.setContentsMargins(0, 0, 0, 0)
        self._files_layout.setSpacing(4)
        self._files_layout.addStretch(1)
        files_scroll.setWidget(self._files_list)

        self._activate_btn = QPushButton("", self)
        self._activate_btn.setObjectName("PrimaryButton")
        self._activate_btn.setCursor(Qt.PointingHandCursor)
        self._activate_btn.setMinimumHeight(52)
        self._activate_btn.clicked.connect(self.activate_clicked)

        self._deactivate_btn = QPushButton("", self)
        self._deactivate_btn.setToolTip("")
        self._deactivate_btn.clicked.connect(self.deactivate_clicked)

        self._delete_btn = QPushButton("", self)
        self._delete_btn.setObjectName("DangerButton")
        self._delete_btn.setToolTip("")
        self._delete_btn.clicked.connect(self.delete_clicked)

        self._open_btn = QPushButton("", self)
        self._open_btn.clicked.connect(self.open_source_clicked)

        self._edit_image_btn = QPushButton("", self)
        self._edit_image_btn.setToolTip("")
        self._edit_image_btn.clicked.connect(self.edit_image_clicked)

        self._add_obj_btn = QPushButton("", self)
        self._add_obj_btn.setToolTip("")
        self._add_obj_btn.clicked.connect(self.add_obj_clicked)

        self._remove_obj_btn = QPushButton("", self)
        self._remove_obj_btn.setObjectName("DangerButton")
        self._remove_obj_btn.setToolTip("")
        self._remove_obj_btn.clicked.connect(self.remove_obj_clicked)

        self._sync_btn = QPushButton("", self)
        self._sync_btn.setObjectName("VerifyButton")
        self._sync_btn.setToolTip("")
        self._sync_btn.clicked.connect(self.verify_clicked)
        self._sync_btn.setIcon(check_icon())
        self._sync_btn.setIconSize(QSize(16, 16))

        self._repair_btn = QPushButton("", self)
        self._repair_btn.setObjectName("RepairButton")
        self._repair_btn.setToolTip("")
        self._repair_btn.clicked.connect(self.repair_clicked)
        self._repair_btn.setIcon(wrench_icon())
        self._repair_btn.setIconSize(QSize(16, 16))
        self._repair_btn.hide()

        self.retranslate()

        # Deux rangées d'actions (au lieu d'une seule de 5 boutons) : à
        # fenêtre étroite rien ne se chevauche et les libellés ne sont pas
        # coupés. Chaque rangée partage l'espace avec des stretchs.
        image_row1 = QHBoxLayout()
        image_row1.setSpacing(10)
        image_row1.addWidget(self._edit_image_btn)
        image_row1.addWidget(self._add_obj_btn)
        image_row1.addWidget(self._remove_obj_btn)
        image_row1.addStretch(1)

        image_row2 = QHBoxLayout()
        image_row2.setSpacing(10)
        image_row2.addWidget(self._sync_btn)
        image_row2.addWidget(self._repair_btn)
        image_row2.addWidget(self._open_btn)
        image_row2.addStretch(1)

        self._result_box = QFrame(self)
        self._result_box.setObjectName("Card")
        self._result_box.hide()
        self._result_label = QLabel("", self._result_box)
        self._result_label.setWordWrap(True)
        self._result_label.setStyleSheet("border: none; background: transparent;")
        box_layout = QVBoxLayout(self._result_box)
        box_layout.setContentsMargins(16, 12, 16, 12)
        box_layout.addWidget(self._result_label)

        # Right column.
        right = QWidget(self)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(14)
        right_layout.addWidget(self._name)
        right_layout.addWidget(self._path)
        right_layout.addSpacing(6)
        right_layout.addWidget(self._files_label)
        right_layout.addWidget(files_scroll)
        right_layout.addWidget(self._deps_box)
        right_layout.addStretch(1)
        right_layout.addWidget(self._result_box)

        actions_row = QHBoxLayout()
        actions_row.setSpacing(10)
        actions_row.addWidget(self._activate_btn, 1)
        actions_row.addWidget(self._deactivate_btn)
        actions_row.addWidget(self._delete_btn)
        right_layout.addLayout(actions_row)
        right_layout.addLayout(image_row1)
        right_layout.addLayout(image_row2)

        body = QHBoxLayout()
        body.setSpacing(36)
        body.addWidget(self._preview, 0, Qt.AlignTop)
        # `right` porte déjà son propre layout (QVBoxLayout(right)) : on
        # ajoute donc le widget, pas le layout, sinon Qt émet
        # « QLayout::addChildLayout: layout already has a parent ».
        body.addWidget(right, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 24, 40, 24)
        layout.addLayout(body)

    # ------------------------------------------------------------------ #
    def set_config(self, item: ConfigItem) -> None:
        self._item = item
        self._name.setText(item.name)
        self._path.setText(str(item.path))
        self._preview.set_path(item.preview, item.name)

        # Files list (the associated obj is shown too, even when it lives in
        # the app cache and is copied under its original name).
        names = [f.name for f in item.files]
        if item.obj is not None and item.obj_name and item.obj_name not in names:
            names.append(item.obj_name)
        while self._files_layout.count() > 1:
            child = self._files_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        for name in names:
            lbl = QLabel(name, self._files_list)
            lbl.setStyleSheet("border: none; background: transparent; color: #9aa3b7;")
            self._files_layout.insertWidget(self._files_layout.count() - 1, lbl)
        self._files_label.setText(t("config.files_included", count=len(names)))

        self._remove_obj_btn.setEnabled(item.obj is not None)
        self._show_dependencies(item)
        self._verification: ConfigVerification | None = None
        self.hide_result()
        self.hide_repair()

    # ------------------------------------------------------------------ #
    def _show_dependencies(self, item: ConfigItem) -> None:
        """Analyse the JSON dependencies and display the compact
        « Dépendances » block (analysis is cached per JSON file).

        OBJ and MP3 are shown as separate sections, each with one ✓/✗ line
        per referenced file, so a configuration needing both is identified
        at a glance. A missing dependency never shows a false success."""
        analysis = analyze_item(item)
        self._deps_label.setText(t("deps.title"))
        if not analysis.valid:
            self._deps_content.setText(
                f"<span style='color:{DANGER};'>{t('deps.invalid_json')}</span>"
            )
            self._deps_box.show()
            return
        if not analysis.obj_required and not analysis.mp3_required:
            self._deps_content.setText(
                f"<span style='color:{SUCCESS};'>{t('deps.none')}</span>"
            )
            self._deps_box.show()
            return

        def section(header: str, files, present) -> list[str]:
            """One dependency group: header + one ✓/✗ line per file + a
            missing note when the group is incomplete."""
            lines = [f"<b>{header}</b>"]
            missing_in_group = False
            for name in files:
                if name in present:
                    lines.append(
                        f"<span style='color:{SUCCESS};'>{t('deps.found', name=name)}</span>"
                    )
                else:
                    missing_in_group = True
                    lines.append(
                        f"<span style='color:{DANGER};'>{t('deps.missing', name=name)}</span>"
                    )
            if missing_in_group:
                lines.append(
                    f"<span style='color:{WARNING};'>{t('deps.missing_note')}</span>"
                )
            return lines

        lines: list[str] = []
        if analysis.obj_required:
            lines += section(
                t("deps.obj_header"), analysis.obj_files, analysis.present_obj_files
            )
        if analysis.mp3_required:
            lines += section(
                t("deps.mp3_header"), analysis.mp3_files, analysis.present_mp3_files
            )
        if analysis.incomplete:
            lines.append(
                f"<span style='color:{WARNING};'>{t('deps.explanation')}</span>"
            )
        self._deps_content.setText("<br>".join(lines))
        self._deps_box.show()

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        """Apply the current language to the static button texts and tooltips
        (called at construction and on language change)."""
        self._activate_btn.setText(t("config.activate"))
        self._activate_btn.setToolTip(t("config.activate_tooltip"))
        self._deactivate_btn.setText(t("config.deactivate"))
        self._deactivate_btn.setToolTip(t("config.deactivate_tooltip"))
        self._delete_btn.setText(t("common.delete"))
        self._delete_btn.setToolTip(t("config.delete_tooltip"))
        self._open_btn.setText(t("config.open_source"))
        self._edit_image_btn.setText(t("config.edit_image"))
        self._edit_image_btn.setToolTip(t("config.edit_image_tooltip"))
        self._add_obj_btn.setText(t("config.add_obj"))
        self._add_obj_btn.setToolTip(t("config.add_obj_tooltip"))
        self._remove_obj_btn.setText(t("config.remove_obj"))
        self._remove_obj_btn.setToolTip(t("config.remove_obj_tooltip"))
        self._sync_btn.setText(t("config.verify"))
        self._sync_btn.setToolTip(t("config.verify_tooltip"))
        self._repair_btn.setText(t("repair.button"))
        self._repair_btn.setToolTip(t("repair.button_tooltip"))
        if hasattr(self, "_item") and self._item is not None:
            self._show_dependencies(self._item)

    # ------------------------------------------------------------------ #
    def set_activation_state(self, state: str) -> None:
        """Update the ACTIVATE button to reflect the real Fleasion state."""
        if state == STATE_ACTIVE:
            self._activate_btn.setText(t("config.active"))
            self._activate_btn.setStyleSheet(
                f"QPushButton#PrimaryButton {{ background-color: {SUCCESS};"
                " border: none; color: #06251b; font-size: 11pt;"
                " padding: 12px 28px; border-radius: 12px; }"
            )
            self._activate_btn.setToolTip(t("config.active_tooltip"))
        elif state == STATE_COPIED:
            self._activate_btn.setText(t("config.copied"))
            self._activate_btn.setStyleSheet(
                f"QPushButton#PrimaryButton {{ background-color: {WARNING};"
                " border: none; color: #2b1d00; font-size: 11pt;"
                " padding: 12px 28px; border-radius: 12px; }"
            )
            self._activate_btn.setToolTip(t("config.copied_tooltip"))
        else:
            self._activate_btn.setText(t("config.activate"))
            self._activate_btn.setStyleSheet("")
            self._activate_btn.setToolTip(t("config.activate_tooltip"))
        # Désactiver n'a de sens que lorsqu'un état actif/copié existe.
        self._deactivate_btn.setVisible(state in (STATE_ACTIVE, STATE_COPIED))
        # Désactiver n'a de sens que lorsqu'un état actif/copié existe.
        self._deactivate_btn.setVisible(state in (STATE_ACTIVE, STATE_COPIED))

    # ------------------------------------------------------------------ #
    def hide_result(self) -> None:
        self._result_box.hide()

    def hide_repair(self) -> None:
        """Masquer le bouton Réparer (par défaut — il n'apparaît que quand
        une réparation est réellement pertinente)."""
        self._repair_btn.hide()

    def show_repair(self, verification: ConfigVerification) -> None:
        """Afficher le bouton Réparer quand la configuration est incomplète
        et qu'une réparation est pertinente (JSON valide mais dépendance
        manquante, etc.)."""
        relevant = (
            verification is not None
            and verification.deps is not None
            and bool(verification.deps.missing_obj_files or verification.deps.missing_mp3_files)
        )
        self._repair_btn.setVisible(relevant)

    def show_verification(self, verification: ConfigVerification) -> None:
        """Afficher le résultat de la vérification (« Vérifier », v1.3.0).

        « Configuration valide » (vert) ou « Configuration incomplète »
        (orange) avec la liste précise des problèmes — jamais de faux
        succès : une dépendance manquante rend la configuration
        incomplète, quoi qu'il arrive par ailleurs.
        """
        self._verification = verification
        if verification.valid:
            self._result_box.setStyleSheet(
                f"QFrame#Card {{ background-color: rgba(52, 211, 153, 0.08);"
                f" border: 1px solid {SUCCESS}; border-radius: 14px; }}"
            )
            lines = [t("verify.valid")]
            if verification.deps is not None and (
                verification.deps.obj_required or verification.deps.mp3_required
            ):
                lines.append(t("verify.deps_ok"))
            self._result_label.setText("\n".join(lines))
        else:
            self._result_box.setStyleSheet(
                f"QFrame#Card {{ background-color: rgba(251, 191, 36, 0.08);"
                f" border: 1px solid {WARNING}; border-radius: 14px; }}"
            )
            lines = [t("verify.incomplete")]
            problems = verification.problems
            if problems:
                lines.append("")
                lines.extend(f"• {p}" for p in problems)
            if verification.deps is not None and verification.deps.incomplete:
                lines.append("")
                lines.append(t("verify.usable_note"))
            self._result_label.setText("\n".join(lines))
        self._result_box.show()
        self.show_repair(verification)

    def current_verification(self) -> ConfigVerification | None:
        """La dernière vérification affichée (pour le plan de réparation)."""
        return self._verification

    def show_sync_report(self, report: SyncReport) -> None:
        """Display the outcome of a synchronization in the result box."""
        if report.errors:
            self._result_box.setStyleSheet(
                f"QFrame#Card {{ background-color: rgba(248, 113, 113, 0.08);"
                f" border: 1px solid {DANGER}; border-radius: 14px; }}"
            )
            lines = "\n".join(f"• {e}" for e in report.errors)
            self._result_label.setText(t("config.sync_error", lines=lines))
        else:
            self._result_box.setStyleSheet(
                f"QFrame#Card {{ background-color: rgba(52, 211, 153, 0.08);"
                f" border: 1px solid {SUCCESS}; border-radius: 14px; }}"
            )
            lines = [t("config.sync_ok", summary=report.summary())]
            for entry in report.entries:
                if entry.issue == ISSUE_STALE_COPY:
                    lines.append(t("config.sync_stale", name=entry.name))
                elif entry.issue == ISSUE_UNMANAGED:
                    lines.append(t("config.sync_unmanaged", name=entry.name))
            self._result_label.setText("\n".join(lines))
        self._result_box.show()

    def show_result(self, result: ActivationOutcome, real_state: str | None = None) -> None:
        """Display the outcome of an activation.

        ``real_state`` is the state re-read from Fleasion *after* the action
        (``fleasion.status()``) — Fleasion stays the source of truth. When
        provided, the displayed state follows it: « ACTIF » is only shown
        when the re-read really confirms the activation, never a false
        success. When omitted (unit call), the state is derived from the
        outcome.
        """
        if real_state is None:
            real_state = (
                STATE_ACTIVE
                if result.selected
                else STATE_COPIED
                if result.needs_manual_selection and result.ok
                else STATE_INACTIVE
            )

        if real_state == STATE_ACTIVE:
            self._result_box.setStyleSheet(
                f"QFrame#Card {{ background-color: rgba(52, 211, 153, 0.08);"
                f" border: 1px solid {SUCCESS}; border-radius: 14px; }}"
            )
            self._result_label.setText(
                t("config.activated", summary=result.summary())
            )
            self.set_activation_state(STATE_ACTIVE)
        elif real_state == STATE_COPIED:
            self._result_box.setStyleSheet(
                f"QFrame#Card {{ background-color: rgba(251, 191, 36, 0.08);"
                f" border: 1px solid {WARNING}; border-radius: 14px; }}"
            )
            lines = [t("config.copied_result", summary=result.summary())]
            if result.errors:
                lines.append("")
                lines.extend(f"• {e}" for e in result.errors)
            self._result_label.setText("\n".join(lines))
            self.set_activation_state(STATE_COPIED)
        elif result.ok:
            # Fichiers copiés, mais l'état réel ne confirme rien de plus :
            # jamais affiché comme « actif ».
            self._result_box.setStyleSheet(
                f"QFrame#Card {{ background-color: rgba(251, 191, 36, 0.08);"
                f" border: 1px solid {WARNING}; border-radius: 14px; }}"
            )
            self._result_label.setText(
                t("config.copied_unconfirmed", summary=result.summary())
            )
            self.set_activation_state(STATE_COPIED)
        else:
            self._result_box.setStyleSheet(
                f"QFrame#Card {{ background-color: rgba(248, 113, 113, 0.08);"
                f" border: 1px solid {DANGER}; border-radius: 14px; }}"
            )
            lines = "\n".join(f"• {e}" for e in result.errors)
            self._result_label.setText(t("config.activation_failed", lines=lines))
        self._result_box.show()

    def show_deactivate_result(self, outcome: DeactivateOutcome) -> None:
        """Display the outcome of a deactivation in the result box."""
        if outcome.errors:
            self._result_box.setStyleSheet(
                f"QFrame#Card {{ background-color: rgba(248, 113, 113, 0.08);"
                f" border: 1px solid {DANGER}; border-radius: 14px; }}"
            )
            lines = "\n".join(f"• {e}" for e in outcome.errors)
            self._result_label.setText(t("config.deactivation_error", lines=lines))
        else:
            self._result_box.setStyleSheet(
                f"QFrame#Card {{ background-color: rgba(52, 211, 153, 0.08);"
                f" border: 1px solid {SUCCESS}; border-radius: 14px; }}"
            )
            self._result_label.setText(
                t("config.deactivated", summary=outcome.summary())
            )
        self._result_box.show()
