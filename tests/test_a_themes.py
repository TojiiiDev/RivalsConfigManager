"""Tests for the v1.3.0 theme system.

The theme registry lives in app/themes.py (pure data), the QSS builder and
apply_theme in ui/theme.py. Assertions cover: preset list, custom theme
build, persistence in AppSettings, hot re-application, and the guarantee
that the historical dark colors (public contract of the UI tests) are
never changed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import AppSettings
from app.themes import THEMES, ThemeSpec, custom_theme_spec, spec_for, theme_keys


# ---------------------------------------------------------------------- #
# Registry
# ---------------------------------------------------------------------- #
def test_theme_registry_has_expected_presets() -> None:
    for key in ("dark", "light", "blue", "red", "green", "purple", "midnight"):
        assert key in THEMES, key
        spec = THEMES[key]
        assert isinstance(spec, ThemeSpec)
        assert spec.key == key
        # Chaque couleur est un hex valide.
        for color in (
            spec.bg, spec.bg_alt, spec.card, spec.card_hover, spec.card_active,
            spec.border, spec.border_hover, spec.input_bg, spec.text, spec.text_dim,
            spec.accent, spec.accent_hover, spec.accent_dark,
            spec.success, spec.warning, spec.danger,
        ):
            assert color.startswith("#") and len(color) == 7, (key, color)


def test_dark_theme_keeps_historical_colors() -> None:
    """Contrat public : les tests UI existants assercent ces hex exacts."""
    dark = THEMES["dark"]
    assert dark.accent == "#4f8cff"
    assert dark.danger == "#f87171"
    assert dark.success == "#34d399"
    assert dark.warning == "#fbbf24"
    assert dark.bg == "#0e1116"


def test_theme_keys_matches_registry() -> None:
    # ``custom`` est ajouté par theme_keys() aux presets du registre.
    assert set(theme_keys()) == set(THEMES) | {"custom"}


def test_custom_theme_overrides_colors() -> None:
    """v1.3.1 : chaque champ pilote une vraie couleur — « Accent » et
    « Couleur secondaire » modifient réellement le thème (correction du
    bug où seul primary/fond changeait)."""
    spec = custom_theme_spec(
        primary="#112233", secondary="#223344", accent="#334455",
        background="#445566", gradient=True, gradient_angle=45,
    )
    assert spec.key == "custom"
    assert spec.accent == "#112233"  # « Couleur principale » -> accent d'action
    # « Accent » pilote la nuance action (hover éclairci, jamais la couleur
    # brute) — il change réellement le thème (v1.3.1).
    from app.themes import _lighten

    assert spec.accent_hover == _lighten("#334455", 0.12)
    assert spec.accent_hover != "#112233"
    assert spec.border_hover == "#223344"  # « Couleur secondaire » -> bordures
    assert spec.gradient is not None
    assert spec.gradient_angle == 45


def test_custom_theme_no_gradient() -> None:
    spec = custom_theme_spec(primary="#112233", secondary="#223344",
                             accent="#334455", background="#000000")
    assert spec.gradient is None


def test_spec_for_custom_with_dict() -> None:
    spec = spec_for("custom", {"primary": "#112233", "background": "#000000"})
    assert spec.key == "custom"
    assert spec.accent == "#112233"


def test_spec_for_unknown_key_falls_back_to_default() -> None:
    spec = spec_for("nonexistent-theme")
    assert spec.key == "dark"


# ---------------------------------------------------------------------- #
# Persistence
# ---------------------------------------------------------------------- #
def test_theme_persisted_in_settings(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    settings = AppSettings()
    settings.theme = "blue"
    settings.save()
    assert AppSettings.load().theme == "blue"


def test_theme_unknown_value_falls_back_safely(tmp_path: Path, monkeypatch) -> None:
    appdata = tmp_path / "AppData"
    monkeypatch.setenv("APPDATA", str(appdata))
    d = appdata / "RivalsConfigManager"
    d.mkdir(parents=True)
    (d / "settings.json").write_text(json.dumps({"theme": "not-a-theme"}), encoding="utf-8")
    settings = AppSettings.load()
    assert settings.theme in theme_keys()
    assert settings.theme == "dark"  # défaut


def test_custom_theme_palette_persisted(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    settings = AppSettings()
    settings.theme = "custom"
    settings.custom_theme = {"primary": "#123456", "background": "#000000"}
    settings.save()
    reloaded = AppSettings.load()
    assert reloaded.theme == "custom"
    assert reloaded.custom_theme == {"primary": "#123456", "background": "#000000"}


# ---------------------------------------------------------------------- #
# Hot application (offscreen QApplication)
# ---------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def test_apply_theme_returns_spec_and_sets_stylesheet(qapp, tmp_path: Path, monkeypatch) -> None:
    from ui.theme import apply_theme, active_spec

    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    AppSettings().save()
    spec = apply_theme(qapp, "blue")
    assert spec.key == "blue"
    assert active_spec().key == "blue"
    # Le stylesheet de l'application contient bien les couleurs du thème.
    qss = qapp.styleSheet()
    assert spec.accent in qss


def test_apply_theme_custom(qapp, tmp_path: Path, monkeypatch) -> None:
    from ui.theme import apply_theme, active_spec

    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    AppSettings().save()
    custom = {"primary": "#ff0000", "secondary": "#00ff00", "accent": "#0000ff",
              "background": "#101010"}
    from app.themes import _lighten

    apply_theme(qapp, "custom", custom)
    assert active_spec().key == "custom"
    # primary -> accent d'action ; le champ « Accent » (#0000ff) pilote la
    # nuance hover ; « Couleur secondaire » (#00ff00) pilote les bordures —
    # chaque couleur est réellement appliquée (v1.3.1).
    assert active_spec().accent == "#ff0000"
    assert active_spec().accent_hover == _lighten("#0000ff", 0.12)
    assert active_spec().border_hover == "#00ff00"
    qss = qapp.styleSheet()
    assert active_spec().accent_hover in qss
    assert active_spec().border_hover in qss


def test_custom_theme_apply_persist_and_restart(qapp, tmp_path: Path, monkeypatch) -> None:
    """v1.3.1 : changer les 4 couleurs personnalisées modifie réellement le
    stylesheet, le réglage est persistant et restauré au redémarrage."""
    from ui.theme import active_spec, apply_theme

    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    AppSettings().save()
    palette = {
        "primary": "#ff0000",
        "secondary": "#00ff00",
        "accent": "#0000ff",
        "background": "#0a0a0a",
        "gradient": True,
        "gradient_angle": 135,
    }
    apply_theme(qapp, "custom", palette)
    spec = active_spec()
    assert spec.accent == "#ff0000"
    assert spec.border_hover == "#00ff00"
    assert spec.bg == "#0a0a0a"
    qss = qapp.styleSheet()
    assert spec.accent in qss and spec.border_hover in qss and spec.bg in qss

    # Persistence + restauration au « redémarrage ».
    settings = AppSettings()
    settings.theme = "custom"
    settings.custom_theme = palette
    settings.save()
    reloaded = AppSettings.load()
    assert reloaded.theme == "custom"
    assert reloaded.custom_theme["accent"] == "#0000ff"

    apply_theme(qapp, reloaded.theme, reloaded.custom_theme)
    spec2 = active_spec()
    assert spec2.bg == "#0a0a0a"
    assert spec2.border_hover == "#00ff00"
