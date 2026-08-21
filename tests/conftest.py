"""Shared pytest fixtures."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Make the project root importable.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Run the GUI tests headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# No network in tests: the asset sync must default to a disabled remote
# (an empty RCM_ASSET_BASE_URL explicitly overrides the baked-in default).
os.environ["RCM_ASSET_BASE_URL"] = ""

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_onboarding_auto(monkeypatch):
    """L'onboarding (v1.3.8) est désactivé par défaut dans les tests :
    construire une fenêtre ne doit jamais ouvrir un modal de choix de
    langue ni l'overlay du tutoriel. Seuls les tests d'onboarding
    l'activent explicitement (``RCM_ONBOARDING=1``)."""
    monkeypatch.setenv("RCM_ONBOARDING", "0")


@pytest.fixture(autouse=True)
def _never_touch_real_fleasion(monkeypatch):
    """Sécurité de la suite : le VRAI processus Fleasion de la machine ne
    doit jamais être fermé/relancé pendant les tests. Par défaut Fleasion
    est considéré comme « non lancé » (aucun redémarrage). Les tests qui
    veulent exercer la détection réelle ou le hot reload désactivent ce
    garde-fou localement (``fr._TESTS_DISABLE_REAL = False``)."""
    import app.fleasion_restart as fr

    original = fr.find_fleasion_processes

    def _safe(*args, **kwargs):
        if getattr(fr, "_TESTS_DISABLE_REAL", False):
            return []
        return original(*args, **kwargs)

    monkeypatch.setattr(fr, "find_fleasion_processes", _safe)
    monkeypatch.setattr(fr, "_TESTS_DISABLE_REAL", True, raising=False)


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


@pytest.fixture
def library(tmp_path: Path) -> Path:
    """A synthetic library mirroring the real structure, with spaces in names."""
    root = tmp_path / "Rivals configs"

    # Flat categories: one JSON per configuration.
    write_json(root / "Charms" / "nemesis charm.json", {"replacement_rules": []})
    write_json(root / "Charms" / "plat 1 seas 2 arch.json", {"replacement_rules": []})

    write_json(root / "emotes" / "flossswap (1).json", {"replacement_rules": []})

    # FastFlags: same shape but a different JSON payload.
    write_json(root / "FastFlags" / "Fleasion FastFlags.json", {"DFFlagTest": "True"})

    # Skin folder: weapon type -> weapon -> several skins (navigation).
    ak = root / "rivals skins" / "Primary" / "Assault Rifle"
    write_json(ak / "ak-47.json", {"replacement_rules": []})
    write_json(ak / "key up.json", {"replacement_rules": []})

    # Weapon with a single skin -> config named after the JSON.
    axe = root / "rivals skins" / "Melee" / "Battle Axe"
    write_json(axe / "NordicAxe.json", {"replacement_rules": []})

    # Weapon whose skin references a local mesh (dependency resolution).
    gun = root / "rivals skins" / "Secondary" / "Hand gun"
    write_json(gun / "Pixelhandgun.json", {"replacement_rules": [{"cdn_url": "Pixelboddy.obj"}]})
    write_json(gun / "key handgun.json", {"replacement_rules": []})
    (gun / "Pixelboddy.obj").write_text("mesh data", encoding="utf-8")
    (gun / "pxl mag.obj").write_text("mesh data", encoding="utf-8")

    # Pack folder with a preview image -> single folder configuration.
    pack = root / "Texture and skyboxes" / "Texture packs"
    write_json(pack / "Minecraft_Classic.json", {"replacement_rules": []})
    import base64

    # A real minimal 1x1 PNG so the image loader does not complain.
    (pack / "preview.png").write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
            "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
        )
    )

    # Skybox pack: several JSONs -> navigation node.
    sky = root / "Texture and skyboxes" / "Sky"
    write_json(sky / "cloudly sky.json", {"replacement_rules": []})
    write_json(sky / "pink sky.json", {"replacement_rules": []})

    return root


@pytest.fixture
def fleasion_dir(tmp_path: Path) -> Path:
    """A fake Fleasion config folder."""
    path = tmp_path / "AppData" / "Local" / "FleasionNT" / "config"
    path.mkdir(parents=True, exist_ok=True)
    return path
