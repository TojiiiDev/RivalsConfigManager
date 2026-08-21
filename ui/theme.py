"""Theme application — turns a :class:`app.themes.ThemeSpec` into the
application's palette + stylesheet.

The color definitions live in :mod:`app.themes` (pure data). This module
builds the QSS from the **active** spec and keeps the historical module
constants (``ACCENT``, ``DANGER``, ...) as the *dark* theme's values so
existing imports and inline styles keep working unchanged — the active
theme only changes what :func:`theme_color` returns and the stylesheet.

Call :func:`apply_theme` at startup (and again when the user switches
theme in Settings): it applies the palette, the stylesheet and remembers
the active spec for the inline styles of cards / dialogs / toasts.
"""

from __future__ import annotations

import math

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from app.themes import DEFAULT_THEME, ThemeSpec, spec_for

# ---------------------------------------------------------------------- #
# Historical constants — the DARK theme's values (public contract: several
# UI tests assert these exact hex codes, never change them).
# ---------------------------------------------------------------------- #
BG = "#0e1116"           # window background
BG_ALT = "#131720"       # page background
CARD = "#171c26"         # card background
CARD_HOVER = "#1d2331"   # card hover background
CARD_ACTIVE = "#202839"  # selected card
BORDER = "#232a3a"       # borders
BORDER_HOVER = "#33405c"
INPUT_BG = "#10141c"
TEXT = "#e8ebf2"
TEXT_DIM = "#8b93a7"
ACCENT = "#4f8cff"
ACCENT_HOVER = "#6b9dff"
ACCENT_DARK = "#3a6fd6"
SUCCESS = "#34d399"
WARNING = "#fbbf24"
DANGER = "#f87171"

RADIUS = 14

#: The currently applied spec (starts as the dark default).
_active: ThemeSpec = spec_for(DEFAULT_THEME)

#: Identity of the last fully applied theme — ``app.setStyleSheet`` re-polishes
#: EVERY widget of EVERY window, so re-applying an unchanged theme (e.g. on
#: every MainWindow construction during tests) would be quadratic in the
#: number of live windows. Skip it when nothing changed.
_last_applied: tuple | None = None


def active_spec() -> ThemeSpec:
    """The spec currently applied to the application."""
    return _active


def theme_color(name: str) -> str:
    """A color of the **active** theme by semantic name (for inline styles
    that QSS cannot reach, e.g. buttons painted with explicit colors)."""
    return str(getattr(_active, name, getattr(_active, name)))


# ---------------------------------------------------------------------- #
# QSS builder
# ---------------------------------------------------------------------- #
def _qss(spec: ThemeSpec) -> str:
    bg = spec.bg
    if spec.gradient is not None:
        from_color, to_color = spec.gradient
        angle = getattr(spec, "gradient_angle", 135.0) or 135.0
        x1, y1, x2, y2 = _gradient_coords(angle)
        bg = (
            f"qlineargradient(x1:{x1}, y1:{y1}, x2:{x2}, y2:{y2},"
            f" stop:0 {from_color}, stop:1 {to_color})"
        )
    return f"""
    * {{
        font-family: "Segoe UI", "Segoe UI Variable", sans-serif;
        font-size: 10pt;
        color: {spec.text};
        outline: none;
    }}
    QMainWindow, QWidget#PageRoot {{
        background-color: {bg};
    }}
    QWidget#TopBar {{
        background-color: {spec.bg_alt};
        border-bottom: 1px solid {spec.border};
    }}

    /* ---------------- Titles / labels ---------------- */
    QLabel#AppTitle {{
        font-size: 22pt;
        font-weight: 700;
        color: {spec.text};
    }}
    QLabel#AppSubtitle {{
        font-size: 10.5pt;
        color: {spec.text_dim};
    }}
    QLabel#PageTitle {{
        font-size: 17pt;
        font-weight: 700;
    }}
    QLabel#PageSubtitle {{
        color: {spec.text_dim};
    }}
    QLabel#SectionLabel {{
        color: {spec.text_dim};
        font-size: 9pt;
        font-weight: 600;
        letter-spacing: 1px;
    }}
    QLabel#PathLabel {{
        background-color: {spec.input_bg};
        border: 1px solid {spec.border};
        border-radius: 8px;
        padding: 8px 10px;
        color: {spec.text_dim};
    }}

    /* ---------------- Cards ---------------- */
    /* No border: the layout math in the responsive tests (and the title
       full-row-width guarantee) assumes the content rect equals the card
       rect. Hover/selection are signalled by background colour only. */
    QFrame#Card {{
        background-color: {spec.card};
        border: none;
        border-radius: {RADIUS}px;
    }}
    QFrame#Card:hover {{
        background-color: {spec.card_hover};
    }}
    QFrame#Card[selected="true"] {{
        background-color: {spec.card_active};
    }}
    /* Cellule cible pendant un glisser-déposer de réorganisation :
       indication légère de l'emplacement d'insertion. */
    QWidget#CardCell[drop-target="true"] {{
        border: 2px solid {spec.accent};
        border-radius: 16px;
        background-color: rgba(79, 140, 255, 0.08);
    }}
    QLabel#CardTitle {{
        font-size: 11.5pt;
        font-weight: 600;
    }}
    QLabel#CardSubtitle {{
        color: {spec.text_dim};
        font-size: 9pt;
    }}

    /* ---------------- Buttons ---------------- */
    QPushButton {{
        background-color: {spec.card};
        border: 1px solid {spec.border};
        border-radius: 10px;
        padding: 8px 16px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background-color: {spec.card_hover};
        border-color: {spec.border_hover};
    }}
    QPushButton:pressed {{
        background-color: {spec.card_active};
    }}
    QPushButton:disabled {{
        color: #5b6373;
        background-color: {spec.bg_alt};
        border-color: {spec.border};
    }}
    QPushButton#PrimaryButton {{
        background-color: {spec.accent};
        border: none;
        color: white;
        font-size: 11pt;
        padding: 12px 28px;
        border-radius: 12px;
    }}
    QPushButton#PrimaryButton:hover {{
        background-color: {spec.accent_hover};
    }}
    QPushButton#PrimaryButton:pressed {{
        background-color: {spec.accent_dark};
    }}
    QPushButton#DangerButton {{
        color: {spec.danger};
    }}
    QPushButton#DangerButton:hover {{
        background-color: rgba(248, 113, 113, 0.08);
        border-color: {spec.danger};
    }}
    QPushButton#IconButton {{
        background-color: transparent;
        border: none;
        border-radius: 10px;
        padding: 6px 10px;
        font-size: 12pt;
    }}
    QPushButton#IconButton:hover {{
        background-color: {spec.card_hover};
    }}

    /* ---------------- Inputs ---------------- */
    QLineEdit, QComboBox {{
        background-color: {spec.input_bg};
        border: 1px solid {spec.border};
        border-radius: 10px;
        padding: 9px 14px;
        selection-background-color: {spec.accent};
    }}
    QLineEdit:focus, QComboBox:focus {{
        border-color: {spec.accent};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 26px;
    }}
    QComboBox QAbstractItemView {{
        background-color: {spec.card};
        border: 1px solid {spec.border};
        border-radius: 8px;
        selection-background-color: {spec.accent};
        padding: 4px;
    }}

    /* ---------------- Checkbox ---------------- */
    QCheckBox {{
        spacing: 8px;
    }}
    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 5px;
        border: 1px solid {spec.border_hover};
        background-color: {spec.input_bg};
    }}
    QCheckBox::indicator:checked {{
        background-color: {spec.accent};
        border-color: {spec.accent};
    }}

    /* ---------------- Clear Configs (bottom-right, discreet) ------- */
    QPushButton#ClearButton {{
        background-color: transparent;
        border: none;
        border-radius: 10px;
        padding: 6px 12px;
        color: {spec.text_dim};
        font-size: 9.5pt;
    }}
    QPushButton#ClearButton:hover {{
        background-color: rgba(248, 113, 113, 0.08);
        color: {spec.danger};
    }}

    /* ---------------- Scrollbars ---------------- */
    QScrollArea {{
        border: none;
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {spec.border_hover};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: #46536f;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {spec.border_hover};
        border-radius: 5px;
        min-width: 30px;
    }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
        width: 0;
    }}

    /* ---------------- Dialogs / toasts ---------------- */
    QMessageBox {{
        background-color: {spec.bg_alt};
    }}
    QMessageBox QLabel {{
        font-size: 10.5pt;
    }}
    QDialog {{
        background-color: {spec.bg_alt};
    }}
    QListWidget {{
        background-color: {spec.card};
        border: 1px solid {spec.border};
        border-radius: 10px;
        padding: 6px;
    }}
    QListWidget::item {{
        padding: 8px;
        border-radius: 8px;
    }}
    QListWidget::item:selected {{
        background-color: {spec.accent};
    }}
    QProgressBar {{
        background-color: {spec.input_bg};
        border: 1px solid {spec.border};
        border-radius: 8px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background-color: {spec.accent};
        border-radius: 7px;
    }}
    QToolTip {{
        background-color: {spec.card_active};
        color: {spec.text};
        border: 1px solid {spec.border_hover};
        border-radius: 6px;
        padding: 6px 8px;
    }}
    """


def _gradient_coords(angle: float) -> tuple[float, float, float, float]:
    """Map a gradient angle (degrees) to qlineargradient coordinates.

    0° = left → right, 90° = top → bottom (like CSS linear-gradient).
    """
    rad = math.radians(angle % 360)
    dx = math.cos(rad)
    dy = -math.sin(rad)  # y grows downward in QSS coordinates
    # Normalize so the gradient spans the full area.
    length = max(abs(dx), abs(dy)) or 1.0
    nx, ny = dx / length, dy / length
    return (0.5 - nx / 2, 0.5 - ny / 2, 0.5 + nx / 2, 0.5 + ny / 2)


# ---------------------------------------------------------------------- #
# Public API
# ---------------------------------------------------------------------- #
def apply_theme(app: QApplication, theme_key: str = DEFAULT_THEME,
                custom: dict | None = None) -> ThemeSpec:
    """Apply a theme (preset key or ``"custom"`` + palette dict) to the
    application: palette + stylesheet. Returns the applied spec.

    The module-level color constants are left untouched (they are the dark
    defaults); inline styles must use :func:`theme_color` to follow the
    active theme.
    """
    global _active, _last_applied
    spec = spec_for(theme_key, custom)
    _active = spec

    identity = (theme_key, tuple(sorted((custom or {}).items())))
    if identity == _last_applied:
        # Same theme as the last applied one: nothing to restyle. The
        # spec/_active update above still takes effect for inline styles.
        return spec
    _last_applied = identity

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(spec.bg))
    palette.setColor(QPalette.WindowText, QColor(spec.text))
    palette.setColor(QPalette.Base, QColor(spec.input_bg))
    palette.setColor(QPalette.AlternateBase, QColor(spec.bg_alt))
    palette.setColor(QPalette.Text, QColor(spec.text))
    palette.setColor(QPalette.Button, QColor(spec.card))
    palette.setColor(QPalette.ButtonText, QColor(spec.text))
    palette.setColor(QPalette.Highlight, QColor(spec.accent))
    palette.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ToolTipBase, QColor(spec.card_active))
    palette.setColor(QPalette.ToolTipText, QColor(spec.text))
    palette.setColor(QPalette.PlaceholderText, QColor(spec.text_dim))
    app.setPalette(palette)
    app.setStyleSheet(_qss(spec))
    return spec
