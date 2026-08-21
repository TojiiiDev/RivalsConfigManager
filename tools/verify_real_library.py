"""Vérification réelle avec la bibliothèque complète (lue seule, rien n'est
modifié) : navigation dans les pages clés + redimensionnements + transitions
plein écran, contrôle de la position des étoiles, de l'absence d'étoile sur
les cartes de navigation et des previews."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Jamais d'onboarding (pas de modal) pendant la vérification de la
# bibliothèque réelle : l'outil construit la fenêtre directement.
os.environ.setdefault("RCM_ONBOARDING", "0")

from PySide6.QtWidgets import QApplication

# Chemin de la bibliothèque réelle — fourni par l'environnement au moment
# de l'exécution (variable RCM_REAL_LIB). Le défaut est un chemin neutre,
# résolu par utilisateur : aucun chemin personnel n'est codé en dur.
REAL_LIB = Path(os.environ.get("RCM_REAL_LIB") or (Path.home() / "Desktop" / "Rivals configs"))

SIZES = [(560, 420), (800, 600), (1080, 720), (1600, 1000), (640, 480)]


def overlay_problems(cards):
    problems = []
    for card in cards:
        fav = card.favorite_button
        if fav is not None:
            p = fav.pos()
            inside = (p.x() >= 0 and p.y() >= 0
                      and p.x() + fav.width() <= card.width()
                      and p.y() + fav.height() <= card.height())
            if not inside:
                problems.append(f"{card.drag_key[-40:]}: star({p.x()},{p.y()}) carte {card.width()}x{card.height()}")
    return problems


def preview_problems(cards):
    problems = []
    for card in cards:
        preview = card._preview
        pm = preview.pixmap()
        if pm is None or pm.isNull():
            problems.append(f"{card.drag_key[-40:]}: preview nulle")
            continue
        s = preview.size()
        if s.width() <= 1 or s.height() <= 1:
            problems.append(f"{card.drag_key[-40:]}: preview taille {s.width()}x{s.height()}")
    return problems


def main() -> int:
    if not REAL_LIB.is_dir():
        print(f"Bibliothèque introuvable : {REAL_LIB}")
        return 2
    app = QApplication(sys.argv)
    tmp = Path(tempfile.mkdtemp())
    appdata = tmp / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    os.environ["APPDATA"] = str(appdata)
    fleasion = tmp / "fleasion"
    fleasion.mkdir(parents=True)
    s = appdata / "RivalsConfigManager" / "settings.json"
    s.parent.mkdir(parents=True)
    s.write_text(json.dumps({"library_dir": str(REAL_LIB), "fleasion_dir": str(fleasion)}), encoding="utf-8")
    (fleasion / "settings.json").write_text("{}", encoding="utf-8")

    from app.scanner import find_node
    from ui.main_window import MainWindow

    window = MainWindow()
    window.show()
    app.processEvents()

    pages = [
        ("home", None),
        ("rivals skins", REAL_LIB / "rivals skins"),
        ("primary (catégorie)", REAL_LIB / "rivals skins" / "primary"),
        ("une arme (skins)", REAL_LIB / "rivals skins" / "primary" / "Assult Rifle"),
        ("melee (catégorie)", REAL_LIB / "rivals skins" / "Melee"),
        ("une arme melee", REAL_LIB / "rivals skins" / "Melee" / "Katana"),
        ("Charms", REAL_LIB / "Charms"),
        ("Textures and skyboxes", REAL_LIB / "Textures and skyboxes"),
        ("Texture packs", REAL_LIB / "Textures and skyboxes" / "Texture packs"),
        ("Sky", REAL_LIB / "Textures and skyboxes" / "Sky"),
    ]

    total_bad = 0
    for label, path in pages:
        if path is None:
            window.go(("home", None))
        else:
            node = find_node(window.root_node, path)
            if node is None:
                print(f"[{label}] page introuvable (config folder ?) — ignorée")
                continue
            window.go(("browse", node))
        app.processEvents()
        for width, height in SIZES:
            window.resize(width, height)
            app.processEvents()
        window.showFullScreen()
        app.processEvents()
        window.showNormal()
        window.resize(1080, 720)
        app.processEvents()
        grid = window._current_grid()
        if grid is None:
            continue
        stars = sum(1 for c in grid._cards if c.favorite_button is not None)
        noproblem = overlay_problems(grid._cards)
        badprev = preview_problems(grid._cards)
        total_bad += len(noproblem) + len(badprev)
        print(f"[{label}] cartes={len(grid._cards)} étoiles={stars} "
              f"stars-hors-carte={len(noproblem)} previews-cassées={len(badprev)}")
        for p in (noproblem + badprev)[:4]:
            print("   !", p)

    # Vérification des catégories de navigation (aucune étoile).
    window.go(("home", None))
    app.processEvents()
    home_no_star = [c._title_label.text() for c in window._home._grid._cards if c.favorite_button is not None]
    print("\nCatégories de l'accueil AVEC étoile (doit être vide) :", home_no_star)
    if home_no_star:
        total_bad += len(home_no_star)

    print("\nRESULTAT :", "OK" if total_bad == 0 else f"{total_bad} PROBLEMES")
    window.deleteLater()
    return 0 if total_bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
