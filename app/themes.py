"""Visual themes — central registry (pure data, no Qt).

The whole application reads its colors from here: the QSS builder in
``ui/theme.py`` turns a :class:`ThemeSpec` into the stylesheet, and the
settings layer validates the persisted theme key against
:data:`THEMES`. No color is hard-coded in the views: they all go through
:func:`ui.theme.theme_color` / the generated stylesheet.

A :class:`ThemeSpec` carries every color the stylesheet needs. The default
theme (``dark``) keeps the exact historical values so existing behaviour
and tests are unchanged. ``light``, ``blue``, ``red``, ``green``,
``purple`` and ``midnight`` are coherent preset variants; ``custom`` is
built at runtime from the user's own palette (primary / secondary /
accent / background + optional gradient).
"""

from __future__ import annotations

from dataclasses import dataclass, replace

#: Default theme — the historical dark look. Its hex values are part of the
#: public contract (existing UI tests assert them), never change them.
DEFAULT_THEME = "dark"


@dataclass(frozen=True)
class ThemeSpec:
    """A complete color palette for the application stylesheet."""

    key: str
    label_key: str                 # i18n key of the display name
    bg: str                        # window background
    bg_alt: str                    # page / top bar background
    card: str                      # card background
    card_hover: str                # card hover background
    card_active: str               # selected card
    border: str                    # borders
    border_hover: str              # borders on hover
    input_bg: str                  # inputs background
    text: str
    text_dim: str
    accent: str                    # main action color (buttons, selection)
    accent_hover: str
    accent_dark: str
    success: str
    warning: str
    danger: str
    #: Gradient applied to the window background (``None`` = flat).
    gradient: tuple[str, str] | None = None   # (from_color, to_color)
    #: Gradient direction in degrees (0 = left→right, 90 = top→bottom).
    gradient_angle: float = 135.0


# ---------------------------------------------------------------------- #
# Preset themes
# ---------------------------------------------------------------------- #
THEMES: dict[str, ThemeSpec] = {
    "dark": ThemeSpec(
        key="dark",
        label_key="theme.dark",
        bg="#0e1116",
        bg_alt="#131720",
        card="#171c26",
        card_hover="#1d2331",
        card_active="#202839",
        border="#232a3a",
        border_hover="#33405c",
        input_bg="#10141c",
        text="#e8ebf2",
        text_dim="#8b93a7",
        accent="#4f8cff",
        accent_hover="#6b9dff",
        accent_dark="#3a6fd6",
        success="#34d399",
        warning="#fbbf24",
        danger="#f87171",
    ),
    "light": ThemeSpec(
        key="light",
        label_key="theme.light",
        bg="#f4f6fa",
        bg_alt="#ffffff",
        card="#ffffff",
        card_hover="#eef1f7",
        card_active="#e4eaf6",
        border="#d7dde8",
        border_hover="#b9c4d8",
        input_bg="#ffffff",
        text="#1c2333",
        text_dim="#5c6577",
        accent="#3b6fd6",
        accent_hover="#4f7fe0",
        accent_dark="#2f5bb5",
        success="#12966b",
        warning="#b57f0a",
        danger="#c93b3b",
    ),
    "blue": ThemeSpec(
        key="blue",
        label_key="theme.blue",
        bg="#0a1220",
        bg_alt="#0f1a2e",
        card="#14233c",
        card_hover="#1a2d4d",
        card_active="#1f3559",
        border="#223a5e",
        border_hover="#31537f",
        input_bg="#0d1829",
        text="#e6f0ff",
        text_dim="#8fa8c8",
        accent="#2f7dff",
        accent_hover="#4f95ff",
        accent_dark="#2563d6",
        success="#34d399",
        warning="#fbbf24",
        danger="#f87171",
    ),
    "red": ThemeSpec(
        key="red",
        label_key="theme.red",
        bg="#160e10",
        bg_alt="#1d1214",
        card="#271719",
        card_hover="#331c1f",
        card_active="#3a2024",
        border="#4a2a2e",
        border_hover="#663a40",
        input_bg="#1a1011",
        text="#fdeeef",
        text_dim="#b08f93",
        accent="#e5484d",
        accent_hover="#f05c61",
        accent_dark="#c23a3f",
        success="#34d399",
        warning="#fbbf24",
        danger="#ff7a7a",
    ),
    "green": ThemeSpec(
        key="green",
        label_key="theme.green",
        bg="#0c1410",
        bg_alt="#111b15",
        card="#16241b",
        card_hover="#1d3022",
        card_active="#223a29",
        border="#2b4a35",
        border_hover="#3d664a",
        input_bg="#0e1812",
        text="#e6f5ec",
        text_dim="#8fb3a0",
        accent="#2fbf71",
        accent_hover="#45d484",
        accent_dark="#269a5c",
        success="#34d399",
        warning="#fbbf24",
        danger="#f87171",
    ),
    "purple": ThemeSpec(
        key="purple",
        label_key="theme.purple",
        bg="#100d18",
        bg_alt="#161222",
        card="#1e1830",
        card_hover="#272040",
        card_active="#2d2449",
        border="#3b3057",
        border_hover="#534479",
        input_bg="#130f1e",
        text="#f1ecfb",
        text_dim="#a795c9",
        accent="#8b5cf6",
        accent_hover="#9f72ff",
        accent_dark="#7446d6",
        success="#34d399",
        warning="#fbbf24",
        danger="#f87171",
    ),
    "midnight": ThemeSpec(
        key="midnight",
        label_key="theme.midnight",
        bg="#05070d",
        bg_alt="#0a0e18",
        card="#0e1420",
        card_hover="#141c2c",
        card_active="#182236",
        border="#1e2a40",
        border_hover="#2c3e5e",
        input_bg="#080b13",
        text="#dbe6ff",
        text_dim="#6f82a6",
        accent="#5eead4",
        accent_hover="#7ff0de",
        accent_dark="#43c9b2",
        success="#34d399",
        warning="#fbbf24",
        danger="#f87171",
    ),
}


def theme_keys() -> list[str]:
    """All theme keys (presets + ``custom``), in declaration order."""
    return list(THEMES) + ["custom"]


def is_supported(key: str) -> bool:
    """True when ``key`` is a known theme (preset or ``custom``)."""
    return key in theme_keys()


def default_theme() -> str:
    return DEFAULT_THEME


# ---------------------------------------------------------------------- #
# Custom theme
# ---------------------------------------------------------------------- #
def custom_theme_spec(primary: str, secondary: str, accent: str,
                      background: str, gradient: bool = False,
                      gradient_angle: float = 135.0) -> ThemeSpec:
    """Build the ``custom`` theme from the user's palette.

    The palette follows the Discord-style model: ``primary`` is the main
    brand/action color, ``secondary`` tints hovers and borders, ``accent``
    is used for the selection/checkbox highlight and ``background`` is the
    window base. An optional two-stop gradient (from ``background`` to a
    darker shade) is applied to the window background when ``gradient`` is
    True; ``gradient_angle`` (degrees, 0 = left→right, 90 = top→bottom) is
    kept for the stylesheet builder.
    """
    base = THEMES[DEFAULT_THEME]
    return replace(
        base,
        key="custom",
        label_key="theme.custom",
        bg=background,
        bg_alt=_shade(background, -0.04),
        card=_shade(background, 0.05),
        card_hover=_mix(background, secondary, 0.16),
        card_active=_shade(background, 0.13),
        border=_shade(background, 0.18),
        border_hover=secondary,
        input_bg=_shade(background, -0.02),
        # Chaque champ du sélecteur personnalisé pilote une vraie couleur :
        # « Couleur principale » = l'accent d'action (boutons, sélection) ;
        # « Accent » = la nuance action (hover/press des boutons) ;
        # « Couleur secondaire » = bordures et survols ; « Fond » = la base.
        accent=primary,
        accent_hover=_lighten(accent, 0.12),
        accent_dark=_darken(accent, 0.12),
        success=_lighten(base.success, 0.0) if _is_dark(background) else "#12966b",
        warning="#fbbf24" if _is_dark(background) else "#b57f0a",
        danger=_lighten(base.danger, 0.0) if _is_dark(background) else "#c93b3b",
        gradient=(
            (background, _shade(background, -0.22))
            if gradient and gradient_angle is not None else None
        ),
        gradient_angle=float(gradient_angle) if gradient_angle is not None else 135.0,
    )


def spec_for(theme_key: str, custom: dict | None = None) -> ThemeSpec:
    """The effective :class:`ThemeSpec` for a persisted theme key.

    ``custom`` is the user's palette dict (keys: primary, secondary,
    accent, background, gradient, gradient_angle — with sensible defaults
    when missing). Unknown theme keys fall back to the default theme.
    """
    if theme_key == "custom":
        palette = custom if isinstance(custom, dict) else {}
        return custom_theme_spec(
            primary=str(palette.get("primary", THEMES[DEFAULT_THEME].accent)),
            secondary=str(palette.get("secondary", THEMES[DEFAULT_THEME].border_hover)),
            # Accent explicit ; sinon la couleur principale (palettes plus
            # anciennes sans champ « accent ») ; sinon la valeur par défaut.
            accent=str(
                palette.get("accent")
                or palette.get("primary")
                or THEMES[DEFAULT_THEME].accent_hover
            ),
            background=str(palette.get("background", THEMES[DEFAULT_THEME].bg)),
            gradient=bool(palette.get("gradient", False)),
            gradient_angle=float(palette.get("gradient_angle", 135.0)),
        )
    return THEMES.get(theme_key, THEMES[DEFAULT_THEME])


# ---------------------------------------------------------------------- #
# Color helpers (pure string math, no Qt)
# ---------------------------------------------------------------------- #
def _is_dark(hex_color: str) -> bool:
    r, g, b = _rgb(hex_color)
    return (0.299 * r + 0.587 * g + 0.114 * b) < 140


def _lighten(hex_color: str, amount: float) -> str:
    return _mix(hex_color, "#ffffff", amount)


def _darken(hex_color: str, amount: float) -> str:
    return _mix(hex_color, "#000000", amount)


def _shade(hex_color: str, amount: float) -> str:
    """Lighten (positive) or darken (negative) a color slightly."""
    return _lighten(hex_color, amount) if amount >= 0 else _darken(hex_color, -amount)


def _mix(hex_color: str, other: str, amount: float) -> str:
    r1, g1, b1 = _rgb(hex_color)
    r2, g2, b2 = _rgb(other)
    amount = max(0.0, min(1.0, amount))
    r = int(r1 + (r2 - r1) * amount)
    g = int(g1 + (g2 - g1) * amount)
    b = int(b1 + (b2 - b1) * amount)
    return f"#{r:02x}{g:02x}{b:02x}"


def _rgb(hex_color: str) -> tuple[int, int, int]:
    value = hex_color.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return (0, 0, 0)
