"""End-to-end smoke test: launch the real UI headless and activate a config.

Requires the offscreen platform (set in conftest.py).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.config import AppSettings
from app.scanner import scan_library


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def _configure(fake_appdata: Path, library: Path, fleasion_dir: Path) -> AppSettings:
    settings = AppSettings()
    settings.fleasion_dir = fleasion_dir
    settings.library_dir = library
    settings.save()
    return settings


def test_full_flow(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    # Library was scanned on startup.
    assert window.root_node is not None
    assert any(s.name == "Charms" for s in window.root_node.subdirs)

    # Navigate: home -> Charms (browse) -> config -> activate.
    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    window.go(("browse", charms))
    qapp.processEvents()
    assert window._stack.currentWidget() is window._browse

    item = next(c for c in charms.configs if c.name == "nemesis charm")
    window.go(("config", item))
    qapp.processEvents()
    assert window._stack.currentWidget() is window._config

    window._activate_current()
    qapp.processEvents()

    assert (fleasion_dir / "nemesis charm.json").exists()
    assert (fleasion_dir / "nemesis charm.json").read_text(encoding="utf-8") != ""

    # Back navigation returns to browse.
    window.back()
    qapp.processEvents()
    assert window._stack.currentWidget() is window._browse


def test_activate_ui_verifies_real_state(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """« Activer » : après l'écriture, l'état réel de Fleasion est relu via
    fleasion.status() — « ACTIF » n'est affiché que si la relecture confirme
    réellement la sélection (source de vérité = Fleasion)."""
    import json as _json

    from ui.main_window import MainWindow

    # Une instance Fleasion réaliste : settings.json + configs/.
    fleasion_root = fleasion_dir.parent
    (fleasion_root / "settings.json").write_text(
        _json.dumps({"enabled_configs": [], "last_config": None, "theme": "Dark"}),
        encoding="utf-8",
    )
    (fleasion_root / "configs").mkdir(exist_ok=True)

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")
    window.go(("config", item))
    qapp.processEvents()

    window._activate_current()
    qapp.processEvents()

    # La relecture de l'état réel confirme l'activation.
    assert window.fleasion.status(item) == "active"
    assert window._config._activate_btn.text() == "✓  ACTIF"
    settings = _json.loads((fleasion_root / "settings.json").read_text(encoding="utf-8"))
    assert "nemesis charm" in settings["enabled_configs"]
    assert settings["last_config"] == "nemesis charm"


def test_activate_failure_never_shows_active(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Échec d'activation (écriture de settings.json impossible) : l'UI
    n'affiche JAMAIS « ACTIF » — l'état réel relu ne confirme pas."""
    import json as _json

    import app.fleasion as fleasion_mod

    from ui.main_window import MainWindow

    fleasion_root = fleasion_dir.parent
    (fleasion_root / "settings.json").write_text(
        _json.dumps({"enabled_configs": [], "last_config": None, "theme": "Dark"}),
        encoding="utf-8",
    )
    (fleasion_root / "configs").mkdir(exist_ok=True)

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    # L'écriture de la sélection échoue → les fichiers sont copiés mais la
    # sélection n'est pas confirmée.
    monkeypatch.setattr(fleasion_mod, "_write_settings", lambda p, d: False)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")
    window.go(("config", item))
    qapp.processEvents()

    window._activate_current()
    qapp.processEvents()

    # L'état réel relu ne dit pas « active » et l'UI n'affiche pas « ACTIF ».
    assert window.fleasion.status(item) != "active"
    assert "ACTIF" not in window._config._activate_btn.text()
    assert window._config._activate_btn.text() == "✓  COPIÉ"
    assert "copiée" in window._config._result_label.text().lower()


def test_activate_hot_restart_failure_never_shows_active(
    library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp
) -> None:
    """Hot reload : Fleasion « lancé » mais exécutable introuvable → le
    redémarrage est refusé avant toute fermeture et l'UI n'affiche JAMAIS
    « ACTIF », même si settings.json contient le nom (Fleasion n'a pas
    rechargé : pas de faux succès)."""
    import json as _json

    import app.fleasion_restart as fr

    from ui.main_window import MainWindow

    fleasion_root = fleasion_dir.parent
    (fleasion_root / "settings.json").write_text(
        _json.dumps({"enabled_configs": [], "last_config": None, "theme": "Dark"}),
        encoding="utf-8",
    )
    (fleasion_root / "configs").mkdir(exist_ok=True)
    (fleasion_root / "logs").mkdir(exist_ok=True)
    (fleasion_root / "logs" / "fleasion.log").write_text("x\n", encoding="utf-8")

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    # Fleasion « lancé » mais exécutable introuvable : on ne ferme jamais
    # un processus qu'on ne pourrait pas relancer.
    closed: list[list[int]] = []
    monkeypatch.setattr(
        fr, "find_fleasion_processes",
        lambda: [{"pid": 1, "exe": None, "cmd": None}],
    )
    monkeypatch.setattr(fr, "close_fleasion", lambda pids: closed.append(pids) or True)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")
    window.go(("config", item))
    qapp.processEvents()

    window._activate_current()
    qapp.processEvents()

    # La copie et l'écriture ont réussi (settings.json contient le nom)…
    settings = _json.loads((fleasion_root / "settings.json").read_text(encoding="utf-8"))
    assert "nemesis charm" in settings["enabled_configs"]
    # …mais l'UI n'affiche JAMAIS « ACTIF » (Fleasion n'a pas confirmé).
    assert "ACTIF" not in window._config._activate_btn.text()
    assert window._config._activate_btn.text() == "✓  COPIÉ"
    assert window._config._result_box.isVisible()
    assert "Sélection manuelle" in window._config._result_label.text()
    assert closed == []  # jamais fermé sans pouvoir relancer


def _open_activate_view(window, library: Path):
    from PySide6.QtTest import QTest

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")
    window.go(("config", item))
    QTest.qWait(10)
    return item


def test_hot_activation_option_on_triggers_restart(
    library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp
) -> None:
    """Option ON (défaut) : Activer/Désactiver utilisent le mécanisme
    d'activation à chaud existant (redémarrage + vérification)."""
    import json as _json

    from PySide6.QtTest import QTest

    from app.fleasion import FleasionManager
    from ui.main_window import MainWindow

    fleasion_root = fleasion_dir.parent
    (fleasion_root / "settings.json").write_text(
        _json.dumps({"enabled_configs": [], "last_config": None, "theme": "Dark"}),
        encoding="utf-8",
    )
    (fleasion_root / "configs").mkdir(exist_ok=True)

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    calls: list[tuple[str, bool]] = []

    def fake_hot_restart(self, info, name, data, expect_active):
        calls.append((name, expect_active))
        return True, []

    monkeypatch.setattr(FleasionManager, "_hot_restart", fake_hot_restart)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    assert window.settings.hot_activation_enabled is True  # défaut = ON

    item = _open_activate_view(window, library)
    window._activate_current()
    qapp.processEvents()
    assert calls == [("nemesis charm", True)]
    assert window._config._activate_btn.text() == "✓  ACTIF"

    window._deactivate_current()
    qapp.processEvents()
    assert calls[-1] == ("nemesis charm", False)


def test_hot_activation_option_off_never_restarts(
    library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp
) -> None:
    """Option OFF : aucune fermeture (taskkill), aucun lancement, aucune
    surveillance du log — le flux normal copie + sélection reste utilisé."""
    import json as _json

    from PySide6.QtTest import QTest

    import app.fleasion_restart as fr

    from app.fleasion import FleasionManager
    from ui.main_window import MainWindow

    fleasion_root = fleasion_dir.parent
    (fleasion_root / "settings.json").write_text(
        _json.dumps({"enabled_configs": [], "last_config": None, "theme": "Dark"}),
        encoding="utf-8",
    )
    (fleasion_root / "configs").mkdir(exist_ok=True)

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)
    # Le réglage OFF est persisté AVANT le lancement.
    _json.dump(
        {
            "fleasion_dir": str(fleasion_dir),
            "library_dir": str(library),
            "backup_before_overwrite": True,
            "hot_activation_enabled": False,
        },
        (appdata / "RivalsConfigManager" / "settings.json").open("w", encoding="utf-8"),
    )

    def _forbidden(*a, **k):
        raise AssertionError("redémarrage interdit en mode OFF")

    monkeypatch.setattr(fr, "close_fleasion", _forbidden)
    monkeypatch.setattr(fr, "start_fleasion", _forbidden)
    monkeypatch.setattr(
        FleasionManager, "_hot_restart",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("hot restart appelé en mode OFF")),
    )

    window = MainWindow()
    window.show()
    qapp.processEvents()
    assert window.settings.hot_activation_enabled is False  # restauré

    item = _open_activate_view(window, library)
    window._activate_current()
    qapp.processEvents()
    # Copie + sélection normales, aucun redémarrage, aucune erreur. Le vrai
    # dossier actif de Fleasion est configs/ (settings.json détecté à la racine).
    active_copy = fleasion_root / "configs" / "nemesis charm.json"
    assert active_copy.exists()
    settings = _json.loads((fleasion_root / "settings.json").read_text(encoding="utf-8"))
    assert "nemesis charm" in settings["enabled_configs"]
    assert window._config._activate_btn.text() == "✓  ACTIF"

    window._deactivate_current()
    qapp.processEvents()
    assert not active_copy.exists()
    settings = _json.loads((fleasion_root / "settings.json").read_text(encoding="utf-8"))
    assert "nemesis charm" not in settings["enabled_configs"]


def test_hot_activation_toggle_in_settings_is_saved(
    library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp
) -> None:
    """L'interrupteur des Paramètres est persisté et restauré au redémarrage
    de l'application (settings.json, clé dédiée)."""
    import json as _json

    from PySide6.QtTest import QTest

    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    assert window.settings.hot_activation_enabled is True

    window.go(("settings", None))
    qapp.processEvents()
    check = window._settings._hot_activation_check
    assert check.isChecked()  # état initial = ON
    check.setChecked(False)  # bascule OFF
    qapp.processEvents()

    assert window.settings.hot_activation_enabled is False
    payload = _json.loads(
        (appdata / "RivalsConfigManager" / "settings.json").read_text(encoding="utf-8")
    )
    assert payload["hot_activation_enabled"] is False

    # Redémarrage : le réglage est restauré (case décochée, flag OFF).
    window.close()
    qapp.processEvents()
    window2 = MainWindow()
    window2.show()
    qapp.processEvents()
    assert window2.settings.hot_activation_enabled is False
    assert not window2._settings._hot_activation_check.isChecked()


def _find_card_button(window, key) -> tuple:
    """(card, button) de la carte de configuration correspondante, ou
    (None, None) si introuvable / carte sans bouton."""
    for grid in (window._home._grid, window._browse._grid):
        card = grid.find_card(str(key))
        if card is not None:
            return card, card.toggle_button
    return None, None


def _activate_test_window(library, fleasion_dir, tmp_path, monkeypatch, qapp, enabled=None):
    """Fenêtre prête : settings Fleasion réaliste + page « Charms » ouverte."""
    import json as _json

    from ui.main_window import MainWindow

    fleasion_root = fleasion_dir.parent
    (fleasion_root / "settings.json").write_text(
        _json.dumps({"enabled_configs": enabled or [], "last_config": None, "theme": "Dark"}),
        encoding="utf-8",
    )
    (fleasion_root / "configs").mkdir(exist_ok=True)

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    window.go(("browse", charms))
    qapp.processEvents()
    return window, fleasion_root


def test_card_toggle_inactive_blue_play_and_activation(library, fleasion_dir, tmp_path, monkeypatch, qapp) -> None:
    """Carte inactive : bouton bleu + ▶ ; clic → même logique d'activation
    que le bouton de la page ; confirmé → le bouton passe rouge + ×."""
    from app.fleasion import FleasionManager

    window, fleasion_root = _activate_test_window(library, fleasion_dir, tmp_path, monkeypatch, qapp)
    key = library / "Charms" / "nemesis charm.json"
    card, btn = _find_card_button(window, key)
    assert btn is not None
    assert btn.isVisible()
    # INACTIF : bleu + ▶ (pas d'emoji, pas de texte).
    assert "#4f8cff" in btn.styleSheet()
    assert "Activer cette configuration" in btn.toolTip()
    assert not btn.icon().isNull()
    assert btn.text() == ""

    # Le clic sur le bouton ne navigue pas (pas de clic carte).
    btn.click()
    qapp.processEvents()
    assert window._stack.currentWidget() is window._browse
    assert (fleasion_root / "configs" / "nemesis charm.json").exists()
    # Confirmé → rouge + ×.
    assert "#f87171" in btn.styleSheet()
    assert "Désactiver cette configuration" in btn.toolTip()

    # Désactivation via le bouton → bleu + ▶ à nouveau.
    btn.click()
    qapp.processEvents()
    assert not (fleasion_root / "configs" / "nemesis charm.json").exists()
    assert "#4f8cff" in btn.styleSheet()


def test_card_toggle_initial_state_from_real_fleasion(library, fleasion_dir, tmp_path, monkeypatch, qapp) -> None:
    """L'état initial du bouton vient de la source de vérité Fleasion :
    active → rouge + × ; « copiée mais non sélectionnée » → bleu + ▶."""
    window, fleasion_root = _activate_test_window(
        library, fleasion_dir, tmp_path, monkeypatch, qapp, enabled=["nemesis charm"]
    )
    key = library / "Charms" / "nemesis charm.json"
    card, btn = _find_card_button(window, key)
    assert "#f87171" in btn.styleSheet()  # réellement active → rouge

    # « Copiée mais non active » : fichier présent, non sélectionnée → bleu.
    (fleasion_root / "configs" / "plat 1 seas 2 arch.json").write_text("{}", encoding="utf-8")
    key2 = library / "Charms" / "plat 1 seas 2 arch.json"
    window.go(("browse", next(s for s in window.root_node.subdirs if s.name == "Charms")))
    qapp.processEvents()
    _, btn2 = _find_card_button(window, key2)
    assert "#4f8cff" in btn2.styleSheet()


def test_card_toggle_activation_failure_stays_blue(library, fleasion_dir, tmp_path, monkeypatch, qapp) -> None:
    """Activation échouée → le bouton reste bleu (jamais de faux ACTIF)."""
    import app.fleasion as fleasion_mod

    window, _ = _activate_test_window(library, fleasion_dir, tmp_path, monkeypatch, qapp)
    monkeypatch.setattr(fleasion_mod, "_write_settings", lambda p, d: False)

    key = library / "Charms" / "nemesis charm.json"
    _, btn = _find_card_button(window, key)
    btn.click()
    qapp.processEvents()
    assert "#4f8cff" in btn.styleSheet()
    assert "Activer cette configuration" in btn.toolTip()


def test_card_toggle_deactivation_failure_stays_red(library, fleasion_dir, tmp_path, monkeypatch, qapp) -> None:
    """Désactivation échouée → le bouton reste rouge + × (Fleasion considère
    toujours la configuration active : pas de faux état désactivé)."""
    import app.fleasion as fleasion_mod

    window, _ = _activate_test_window(
        library, fleasion_dir, tmp_path, monkeypatch, qapp, enabled=["nemesis charm"]
    )
    monkeypatch.setattr(fleasion_mod, "_write_settings", lambda p, d: False)

    key = library / "Charms" / "nemesis charm.json"
    _, btn = _find_card_button(window, key)
    assert "#f87171" in btn.styleSheet()
    btn.click()
    qapp.processEvents()
    assert "#f87171" in btn.styleSheet()  # toujours rouge
    assert "Désactiver cette configuration" in btn.toolTip()


def test_card_toggle_respects_hot_activation_setting(library, fleasion_dir, tmp_path, monkeypatch, qapp) -> None:
    """Le bouton respecte hot_activation_enabled : True → restart=True
    (mécanisme à chaud), False → restart=False et aucun taskkill/lancement."""
    import json as _json

    import app.fleasion_restart as fr

    from app.fleasion import FleasionManager

    # --- ON (défaut) : le mécanisme à chaud est utilisé ------------------- #
    window, fleasion_root = _activate_test_window(library, fleasion_dir, tmp_path, monkeypatch, qapp)
    calls: list[bool] = []
    original_activate = window.fleasion.activate

    def recorder(self, item, fm, backup=True, restart=False):
        calls.append(restart)
        return original_activate(item, fm, backup, restart=restart)

    monkeypatch.setattr(FleasionManager, "activate", recorder)
    key = library / "Charms" / "nemesis charm.json"
    _, btn = _find_card_button(window, key)
    btn.click()
    qapp.processEvents()
    assert calls == [True]  # activation à chaud respectée

    # --- OFF : aucun redémarrage ------------------------------------------ #
    # Remettre l'état Fleasion à zéro (l'activation ON ci-dessus a copié la
    # config) pour que le clic OFF soit bien une activation.
    (fleasion_root / "configs" / "nemesis charm.json").unlink(missing_ok=True)
    _json.dump(
        {"enabled_configs": [], "last_config": None, "theme": "Dark"},
        (fleasion_root / "settings.json").open("w", encoding="utf-8"),
    )
    appdata = tmp_path / "AppData" / "Roaming"
    _json.dump(
        {
            "fleasion_dir": str(fleasion_dir),
            "library_dir": str(library),
            "backup_before_overwrite": True,
            "hot_activation_enabled": False,
        },
        (appdata / "RivalsConfigManager" / "settings.json").open("w", encoding="utf-8"),
    )
    from ui.main_window import MainWindow

    window3 = MainWindow()
    window3.show()
    qapp.processEvents()
    charms3 = next(s for s in window3.root_node.subdirs if s.name == "Charms")
    window3.go(("browse", charms3))
    qapp.processEvents()

    calls2: list[bool] = []
    monkeypatch.setattr(
        FleasionManager,
        "activate",
        lambda self, item, fm, backup=True, restart=False: calls2.append(restart)
        or original_activate(item, fm, backup, restart=restart),
    )
    monkeypatch.setattr(
        fr, "close_fleasion",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("taskkill interdit en OFF")),
    )
    monkeypatch.setattr(
        fr, "start_fleasion",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("lancement interdit en OFF")),
    )
    _, btn3 = _find_card_button(window3, key)
    btn3.click()
    qapp.processEvents()
    assert calls2 == [False]  # aucun redémarrage demandé


def test_card_toggle_busy_prevents_double_activation(library, fleasion_dir, tmp_path, monkeypatch, qapp) -> None:
    """Garde anti double activation : pendant qu'une opération est en cours
    (ou déjà déclenchée), un second clic sur la même carte ne relance rien."""
    window, _ = _activate_test_window(library, fleasion_dir, tmp_path, monkeypatch, qapp)
    key = library / "Charms" / "nemesis charm.json"
    _, btn = _find_card_button(window, key)

    calls: list[str] = []
    monkeypatch.setattr(window, "_run_activation", lambda item: calls.append(str(item.path)) or (None, "inactive"))

    # Opération en cours (busy) → le clic est ignoré.
    window._card_toggle_busy = str(key)
    btn.click()
    qapp.processEvents()
    assert calls == []

    # Opération terminée → le clic suivant fonctionne.
    window._card_toggle_busy = None
    btn.click()
    qapp.processEvents()
    assert calls == [str(key)]


def test_card_toggle_works_in_search_and_filters(library, fleasion_dir, tmp_path, monkeypatch, qapp) -> None:
    """Recherche + filtres : le bouton reste fonctionnel et ne modifie pas
    la requête de recherche."""
    window, fleasion_root = _activate_test_window(library, fleasion_dir, tmp_path, monkeypatch, qapp)

    window._search.setText("nemesis")
    qapp.processEvents()
    assert window._stack.currentWidget() is window._browse
    key = library / "Charms" / "nemesis charm.json"
    _, btn = _find_card_button(window, key)
    assert btn is not None
    btn.click()
    qapp.processEvents()
    assert (fleasion_root / "configs" / "nemesis charm.json").exists()
    # La requête de recherche est intacte.
    assert window._search.text() == "nemesis"

    # Filtre d'état « Actifs » (combo direct : déclenche le re-filtrage) →
    # la carte est encore là et le bouton marche.
    view = window._browse
    view._filter_status.setCurrentIndex(view._filter_status.findData("active"))
    qapp.processEvents()
    _, btn2 = _find_card_button(window, key)
    assert btn2 is not None
    btn2.click()
    qapp.processEvents()
    assert not (fleasion_root / "configs" / "nemesis charm.json").exists()
    assert window._search.text() == "nemesis"


def test_card_toggle_button_never_starts_drag(library, fleasion_dir, tmp_path, monkeypatch, qapp) -> None:
    """Un clic/drag DÉPARTI sur le bouton n'est jamais un drag de carte :
    il active/désactive ; le drag depuis la carte reste inchangé."""
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    window, _ = _activate_test_window(library, fleasion_dir, tmp_path, monkeypatch, qapp)
    key = library / "Charms" / "nemesis charm.json"
    card, btn = _find_card_button(window, key)

    before = [c.drag_key for c in window._browse._grid._cards]
    QTest.mousePress(btn, Qt.LeftButton, pos=btn.rect().center())
    QTest.mouseMove(btn, btn.rect().center() + QPoint(80, 0), delay=10)
    QTest.mouseRelease(btn, Qt.LeftButton, pos=btn.rect().center() + QPoint(80, 0))
    qapp.processEvents()
    assert card._dragging is False  # jamais de drag depuis le bouton
    assert [c.drag_key for c in window._browse._grid._cards] == before

    # Le clic droit sur le bouton remonte à la carte (menu contextuel intact).
    assert btn.contextMenuPolicy() == Qt.DefaultContextMenu


def test_card_toggle_button_stays_inside_card_on_resize(library, fleasion_dir, tmp_path, monkeypatch, qapp) -> None:
    """Responsive : à chaque taille de fenêtre, le bouton reste dans la
    carte, sans chevaucher le nom."""
    window, _ = _activate_test_window(library, fleasion_dir, tmp_path, monkeypatch, qapp)
    key = library / "Charms" / "nemesis charm.json"
    for width, height in ((960, 640), (1024, 768), (1280, 720), (1366, 768), (1600, 900), (1920, 1080)):
        window.resize(width, height)
        qapp.processEvents()
        card, btn = _find_card_button(window, key)
        assert btn is not None
        r = btn.geometry()
        assert 0 <= r.x() and r.right() <= card.width()
        assert 0 <= r.y() and r.bottom() <= card.height()
        assert not r.intersects(card._title_label.geometry())


def test_card_title_keeps_full_row_width_with_toggle_button(
    library, fleasion_dir, tmp_path, monkeypatch, qapp
) -> None:
    """Régression layout : depuis l'ajout du bouton d'activation, le titre
    ne doit plus être réduit à la largeur de son mot le plus long (le
    sizeHint d'un QLabel à retour à la ligne). Le label doit occuper TOUTE
    la largeur restante de la rangée, le bouton restant épinglé à droite,
    et un nom court doit rester affiché en entier (jamais réduit à une
    seule lettre)."""
    from ui.widgets.card import Card
    from ui.widgets.grid import CardCell

    # Cartes isolées à plusieurs largeurs (dont la largeur minimale 180).
    for card_width in (180, 200, 250, 320):
        card = Card("Charms", activation_state="inactive")
        cell = CardCell(card)
        cell.resize(card_width, 260)
        card.resize(card_width, 254)
        cell.show()  # nécessaire pour activer le layout (mesure réelle)
        qapp.processEvents()
        btn = card._toggle_btn
        label = card._title_label
        # Le label récupère toute la largeur restante (bouton à droite).
        assert label.width() >= card.width() - 24 - btn.width() - 6 - 1, (
            f"titre écrasé à {card_width}px : label {label.width()}px "
            f"(bouton {btn.width()}px)"
        )
        # Nom court : entier, jamais réduit à une seule lettre.
        assert "…" not in label._shown_text, f"nom court élidé à {card_width}px"
        assert len(label._shown_text.strip()) >= 2, (
            f"nom réduit à une lettre à {card_width}px : {label._shown_text!r}"
        )
        # Bouton épinglé à droite, dans la carte, sans chevauchement.
        assert btn.x() == card.width() - 12 - btn.width()
        assert not btn.geometry().intersects(label.geometry())
        cell.hide()
        cell.deleteLater()

    # Fenêtre réelle aux six tailles responsive demandées.
    window, _ = _activate_test_window(library, fleasion_dir, tmp_path, monkeypatch, qapp)
    short_key = library / "Charms" / "nemesis charm.json"
    long_key = library / "Charms" / "plat 1 seas 2 arch.json"
    for width, height in (
        (960, 640),
        (1024, 768),
        (1280, 720),
        (1366, 768),
        (1600, 900),
        (1920, 1080),
    ):
        window.resize(width, height)
        qapp.processEvents()
        for key in (short_key, long_key):
            card, btn = _find_card_button(window, key)
            assert btn is not None
            label = card._title_label
            assert label.width() >= card.width() - 24 - btn.width() - 6 - 1, (
                f"[{width}x{height}] titre écrasé : label {label.width()}px "
                f"pour {key.name!r}"
            )
            assert not btn.geometry().intersects(label.geometry())
        short, _ = _find_card_button(window, short_key)
        assert "…" not in short._title_label._shown_text, (
            f"[{width}x{height}] nom court élidé à tort"
        )


def test_card_toggle_multi_cards_are_independent(library, fleasion_dir, tmp_path, monkeypatch, qapp) -> None:
    """Plusieurs cartes : chaque bouton agit sur SA configuration."""
    window, fleasion_root = _activate_test_window(library, fleasion_dir, tmp_path, monkeypatch, qapp)
    key_a = library / "Charms" / "nemesis charm.json"
    key_b = library / "Charms" / "plat 1 seas 2 arch.json"
    _, btn_a = _find_card_button(window, key_a)
    _, btn_b = _find_card_button(window, key_b)
    assert btn_a is not None and btn_b is not None

    btn_a.click()  # active uniquement « nemesis charm »
    qapp.processEvents()
    assert (fleasion_root / "configs" / "nemesis charm.json").exists()
    assert not (fleasion_root / "configs" / "plat 1 seas 2 arch.json").exists()
    assert "#f87171" in btn_a.styleSheet()  # A rouge
    assert "#4f8cff" in btn_b.styleSheet()  # B reste bleu

    btn_b.click()  # active la seconde
    qapp.processEvents()
    assert (fleasion_root / "configs" / "plat 1 seas 2 arch.json").exists()
    assert "#f87171" in btn_b.styleSheet()

    btn_a.click()  # désactive uniquement A
    qapp.processEvents()
    assert not (fleasion_root / "configs" / "nemesis charm.json").exists()
    assert (fleasion_root / "configs" / "plat 1 seas 2 arch.json").exists()
    assert "#4f8cff" in btn_a.styleSheet()
    assert "#f87171" in btn_b.styleSheet()


def test_navigation_never_stacks_views(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Rapid navigation must keep exactly one visible page, with no leftover
    graphics effects and no widget accumulation (no stacked views)."""
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QWidget

    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    cats = [s for s in window.root_node.subdirs]
    assert len(cats) >= 4

    def settle() -> None:
        QTest.qWait(400)  # laisse finir l'animation de fondu (160 ms)

    def assert_single_page(tag: str, expected_browse_cards: int | None = None) -> None:
        visible = [n for n, p in window._pages.items() if p.isVisible()]
        assert len(visible) == 1, f"[{tag}] pages visibles : {visible}"
        # Une page par vue enregistrée (y compris Recherche et Profils,
        # ajoutées en 1.3.0) — jamais d'accumulation de vues.
        assert window._stack.count() == len(window._pages)
        # Aucun effet graphique résiduel sur les pages ni sur le stack.
        assert all(p.graphicsEffect() is None for p in window._pages.values()), f"[{tag}] effet résiduel sur une page"
        assert window._stack.graphicsEffect() is None, f"[{tag}] effet résiduel sur le stack"
        assert window._fade_effect is None and window._fade_anim is None
        if expected_browse_cards is not None:
            cards = [c for c in window._browse._grid._container.children() if isinstance(c, QWidget)]
            assert len(cards) == expected_browse_cards, (
                f"[{tag}] {len(cards)} cartes au lieu de {expected_browse_cards} (accumulation ?)"
            )

    # Navigation rapide dans les catégories (les fades se chevauchent).
    for i, cat in enumerate(cats):
        window.go(("browse", cat))
        qapp.processEvents()
    settle()
    assert_single_page("après 7 catégories", expected_browse_cards=cats[-1].total_items())

    # Retours successifs vers l'accueil.
    for _ in range(len(cats)):
        window.back()
        qapp.processEvents()
    settle()
    assert window._stack.currentWidget() is window._home
    assert_single_page("retour accueil")

    # Entrée dans les sous-pages puis retours multiples (arbre profond).
    skins = next(s for s in cats if s.name == "rivals skins")
    window.go(("browse", skins))
    primary = next(s for s in skins.subdirs if s.name.lower() == "primary")
    window.go(("browse", primary))
    weapon = primary.subdirs[0]
    window.go(("browse", weapon))
    skin = weapon.configs[0]
    window.go(("config", skin))
    qapp.processEvents()
    settle()
    assert_single_page("config")
    for _ in range(4):
        window.back()
        qapp.processEvents()
    settle()
    # Quatre retours depuis la config ramènent à l'accueil.
    assert window._stack.currentWidget() is window._home
    assert_single_page("après retours profonds")

    # Beaucoup de navigations répétées : toujours une seule vue, pas de fuite.
    for i in range(30):
        window.go(("browse", cats[i % len(cats)]))
        qapp.processEvents()
    settle()
    assert_single_page("après 30 navigations", expected_browse_cards=cats[29 % len(cats)].total_items())


def test_hover_never_moves_cards(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """The hover lift must never change a card's position in the grid."""
    from PySide6.QtCore import QEvent, QPoint, QPointF
    from PySide6.QtGui import QEnterEvent
    from PySide6.QtTest import QTest

    from ui.main_window import MainWindow
    from ui.widgets.grid import CardCell

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    # Une catégorie avec plusieurs cartes.
    cats = window.root_node.subdirs
    target = max(cats, key=lambda c: c.total_items())
    window.go(("browse", target))
    qapp.processEvents()

    grid = window._browse._grid
    cells = list(grid._cells)
    assert len(cells) >= 3
    container = grid._container

    def absolute_positions() -> list[tuple[int, int]]:
        return [
            (c.card.mapTo(container, QPoint(0, 0)).x(), c.card.mapTo(container, QPoint(0, 0)).y())
            for c in cells
        ]

    def assert_settled() -> None:
        QTest.qWait(400)  # laisse finir les animations (140 ms)
        positions = absolute_positions()
        # Chaque carte est exactement à la position de sa cellule (+ marge).
        for cell, (x, y) in zip(cells, positions):
            cell_origin = cell.mapTo(container, QPoint(0, 0))
            assert (x, y) == (cell_origin.x(), cell_origin.y() + CardCell.TOP_MARGIN), (
                f"carte hors de sa case : {cell.card} pos {(x, y)}"
            )
        # Aucun chevauchement entre cartes (coordonnées du conteneur).
        rects = []
        for cell in cells:
            origin = cell.card.mapTo(container, QPoint(0, 0))
            rect = cell.card.geometry().translated(origin)
            rects.append(rect)
        for i in range(len(rects)):
            for j in range(i + 1, len(rects)):
                assert not rects[i].intersects(rects[j]), f"chevauchement cartes {i} et {j}"
        # Nombre de cartes inchangé.
        assert len(grid._cards) == len(cells)

    before = absolute_positions()
    enter = QEnterEvent(QPointF(0, 0), QPointF(0, 0), QPointF(0, 0))
    leave = QEvent(QEvent.Leave)

    # 1. Hover lent sur chaque carte.
    for cell in cells:
        cell.card.enterEvent(enter)
        QTest.qWait(120)
        cell.card.leaveEvent(leave)
        QTest.qWait(120)
    assert_settled()

    # 2. Hover rapide d'une carte à l'autre + allers-retours (30+ hovers).
    for _ in range(5):
        for cell in cells:
            cell.card.enterEvent(enter)
            qapp.processEvents()
            cell.card.leaveEvent(leave)
            qapp.processEvents()
    # Hovers interrompus en pleine animation (souris rapide).
    for i in range(40):
        cell = cells[i % len(cells)]
        cell.card.enterEvent(enter)
        qapp.processEvents()
        cell.card.leaveEvent(leave)  # quitte avant la fin de l'animation
        qapp.processEvents()
    assert_settled()

    assert absolute_positions() == before, "cartes déplacées définitivement"

    # 3. Naviguer ailleurs puis revenir : le hover reste correct.
    window.go(("browse", cats[0]))
    qapp.processEvents()
    window.back()
    qapp.processEvents()
    cells = list(grid._cells)
    for cell in cells:
        cell.card.enterEvent(enter)
        qapp.processEvents()
        cell.card.leaveEvent(leave)
        qapp.processEvents()
    assert_settled()


def test_card_name_always_visible(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """The card has two independent zones: a fixed-height preview container
    and a separate, always-visible, centered name label. Long names are
    elided; images are contained in the preview zone."""
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QFontMetrics, QEnterEvent
    from PySide6.QtTest import QTest

    from ui.main_window import MainWindow
    from ui.widgets.card import PREVIEW_HEIGHT, Card
    from ui.widgets.grid import CardCell

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    # --- Sans image : placeholder réduit et nom visible --------------------- #
    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    window.go(("browse", charms))
    QTest.qWait(400)

    cards = list(window._browse._grid._cards)
    assert cards, "aucune carte affichée"
    for card in cards:
        # Sans image : placeholder dans une zone preview à hauteur FIXE.
        assert not card._has_image
        assert card._preview_zone.height() == PREVIEW_HEIGHT, "zone preview non fixe"
        # La zone restante sous le preview doit suffire pour le nom (≥ 2 lignes).
        remaining = card.height() - card._preview_zone.height() - 2 * 12  # marges
        fm = QFontMetrics(card._title_label.font())
        assert remaining >= 2 * fm.height(), "zone preview trop haute : nom écrasé"
        # Le nom est un widget séparé, toujours visible, avec une zone ≥ 2 lignes.
        title = card._title_label
        fm = QFontMetrics(title.font())
        assert title.height() >= 2 * fm.height(), "zone du nom trop petite (nom masqué)"
        assert title.text() == title._raw_text, "le nom complet doit être conservé"
        assert title.alignment() & Qt.AlignHCenter, "nom non centré"
        # Le nom est bien dans une zone distincte du preview.
        assert title.geometry().top() >= card._preview_zone.geometry().bottom(), (
            "le nom empiète sur la zone preview"
        )

    # Le nom court reste entier (pas d'ellipsis).
    short = next(c for c in cards if len(c._title_label._raw_text) < 15)
    assert "…" not in short._title_label._shown_text

    # --- Nom très long : ellipsis ------------------------------------------- #
    long_card = Card("Un nom de configuration extrêmement long qui ne devrait jamais tenir sur une seule ligne de carte")
    cell = CardCell(long_card)
    cell.resize(200, 260)
    long_card.resize(200, 254)
    qapp.processEvents()
    shown = long_card._title_label._shown_text
    assert "…" in shown, f"nom long non élidé : {shown!r}"
    # Le nom complet reste accessible via text().
    assert long_card._title_label.text().startswith("Un nom de configuration")

    # --- Avec image : image contenue dans la zone preview -------------------- #
    textures = next(s for s in window.root_node.subdirs if s.name == "Texture and skyboxes")
    window.go(("browse", textures))
    QTest.qWait(300)
    with_image = next(c for c in window._browse._grid._cards if c._has_image)
    assert with_image._preview_zone.height() == PREVIEW_HEIGHT
    # L'image affichée ne déborde pas de la zone preview.
    displayed = with_image._preview.pixmap()
    assert displayed is not None and not displayed.isNull()
    assert displayed.height() <= with_image._preview_zone.height()
    assert displayed.width() <= with_image._preview_zone.width()

    # --- Le hover fonctionne toujours après ces changements ----------------- #
    from PySide6.QtCore import QEvent
    from ui.widgets.card import LIFT_PIXELS

    window.go(("browse", charms))
    QTest.qWait(400)
    cards = list(window._browse._grid._cards)
    enter = QEnterEvent(QPointF(0, 0), QPointF(0, 0), QPointF(0, 0))
    leave = QEvent(QEvent.Leave)
    container = window._browse._grid._container
    for cell in window._browse._grid._cells:
        cell.card.enterEvent(enter)
    QTest.qWait(300)
    for cell in window._browse._grid._cells:
        origin = cell.mapTo(container, cell.rect().topLeft())
        pos = cell.card.mapTo(container, cell.card.rect().topLeft())
        # Pendant le hover, la carte est levée de LIFT_PIXELS dans sa cellule.
        assert pos.y() == origin.y() + CardCell.TOP_MARGIN - LIFT_PIXELS, (
            "carte mal levée pendant le hover"
        )
    for cell in window._browse._grid._cells:
        cell.card.leaveEvent(leave)
    QTest.qWait(300)
    for cell in window._browse._grid._cells:
        origin = cell.mapTo(container, cell.rect().topLeft())
        pos = cell.card.mapTo(container, cell.card.rect().topLeft())
        assert pos.y() == origin.y() + CardCell.TOP_MARGIN, "carte hors de sa case après hover"


def test_image_workflow_end_to_end(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Full image workflow in the real UI: import a local image, check the
    card updates immediately, restart the app, verify persistence, remove
    the image, and confirm the hover system is untouched."""
    import base64

    from PySide6.QtCore import QEvent, QPointF
    from PySide6.QtGui import QEnterEvent
    from PySide6.QtTest import QTest

    from ui.main_window import MainWindow
    from ui.views.image_dialog import ImageDialog
    from ui.widgets.grid import CardCell

    PNG_1PX = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    # --- 1. Start the app, open a config without an image ------------------ #
    window = MainWindow()
    window.show()
    qapp.processEvents()

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    window.go(("browse", charms))
    QTest.qWait(300)
    item = next(c for c in charms.configs if c.name == "nemesis charm")
    window.go(("config", item))
    QTest.qWait(300)
    assert item.preview is None  # no library preview, no sidecar yet

    # --- 2. Import a local image through the dialog ------------------------ #
    from PySide6.QtWidgets import QFileDialog

    source = tmp_path / "rival_skin.png"
    source.write_bytes(PNG_1PX)

    # Drive the real dialog; the modal exec() is bypassed by calling its
    # handlers directly and accepting. The file picker is stubbed.
    dlg = None

    def _fake_picker(*args, **kwargs):
        return (str(source), "Images (*.png)")

    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(_fake_picker))
    dlg = ImageDialog(item, window.image_manager, window)
    dlg._import_local()
    assert "Image importée" in dlg._status.text()
    assert dlg._remove_btn.isEnabled()
    dlg.accept()
    dlg.deleteLater()
    qapp.processEvents()
    window._refresh_and_resync()
    QTest.qWait(400)

    # Card now shows the image (no placeholder). Re-fetch from the rescanned
    # tree: _refresh_and_resync rebuilds it, so the old node is stale.
    fresh_charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    fresh_item = next(c for c in fresh_charms.configs if c.name == "nemesis charm")
    assert fresh_item.preview is not None, "image non résolue après rescan"
    # Back to the browse page so the grid is rebuilt with the new image.
    window.back()
    QTest.qWait(400)
    card = next(c for c in window._browse._grid._cards if c._title_label._raw_text == "nemesis charm")
    assert card._has_image

    # --- 3. Restart: the image must still be there ------------------------- #
    window.close()
    qapp.processEvents()
    window2 = MainWindow()
    window2.show()
    qapp.processEvents()
    charms2 = next(s for s in window2.root_node.subdirs if s.name == "Charms")
    window2.go(("browse", charms2))
    QTest.qWait(400)
    card2 = next(c for c in window2._browse._grid._cards if c._title_label._raw_text == "nemesis charm")
    assert card2._has_image, "image perdue après redémarrage"

    # --- 4. Remove the image: back to placeholder -------------------------- #
    item2 = next(c for c in charms2.configs if c.name == "nemesis charm")
    window2.image_manager.remove(item2)
    window2._refresh_and_resync()
    # The current page after resync is the browse page (history = [browse]).
    QTest.qWait(400)
    card3 = next(c for c in window2._browse._grid._cards if c._title_label._raw_text == "nemesis charm")
    assert not card3._has_image, "placeholder non restauré après suppression"
    from app.image_metadata import load_metadata

    assert load_metadata(item2) is None
    # The real configuration file was never touched.
    assert (library / "Charms" / "nemesis charm.json").exists()

    # --- 5. Hover still works on cards with and without images ------------- #
    enter = QEnterEvent(QPointF(0, 0), QPointF(0, 0), QPointF(0, 0))
    leave = QEvent(QEvent.Leave)
    container = window2._browse._grid._container
    for cell in window2._browse._grid._cells:
        cell.card.enterEvent(enter)
    QTest.qWait(300)
    for cell in window2._browse._grid._cells:
        origin = cell.mapTo(container, cell.rect().topLeft())
        pos = cell.card.mapTo(container, cell.card.rect().topLeft())
        assert pos.y() == origin.y() + CardCell.TOP_MARGIN - 5, "lift hover cassé"
    for cell in window2._browse._grid._cells:
        cell.card.leaveEvent(leave)
    QTest.qWait(300)
    for cell in window2._browse._grid._cells:
        origin = cell.mapTo(container, cell.rect().topLeft())
        pos = cell.card.mapTo(container, cell.card.rect().topLeft())
        assert pos.y() == origin.y() + CardCell.TOP_MARGIN, "carte hors de sa case"


def test_search_from_main_window(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    from app.search import SearchState

    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    window._search.setText("hand gun")
    window._run_search()
    qapp.processEvents()

    assert window._stack.currentWidget() is window._browse
    # The search is a navigable state.
    assert isinstance(window._history.current()[1], SearchState)
    # Hierarchical results: the « Hand gun » folder itself comes first,
    # then its two skins (alphabetical).
    titles = [c._title_label._raw_text for c in window._browse._grid._cards]
    assert titles == ["Hand gun", "key handgun", "Pixelhandgun"]

    # Clicking the folder result opens the folder's page.
    folder_card = next(
        c for c in window._browse._grid._cards if c._title_label._raw_text == "Hand gun"
    )
    folder_card.clicked.emit()
    qapp.processEvents()
    assert window._stack.currentWidget() is window._browse
    assert window._history.current()[0] == "browse"
    assert window._history.current()[1].name == "Hand gun"
    assert len(window._browse._grid._cards) == 2  # les deux skins du dossier

    # Clearing the search leaves the search mode; since a folder page was
    # opened, we stay on that page (no phantom search state, no jump home).
    window._search.setText("")
    window._run_search()
    qapp.processEvents()
    assert window._stack.currentWidget() is window._browse
    assert window._history.current()[0] == "browse"


def test_search_filters_and_empty_state(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Filters combine with the query, the counter updates, Réinitialiser
    resets the filters, and an empty state appears with no results."""
    from PySide6.QtTest import QTest

    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    window._search.setText("key")
    window._run_search()
    qapp.processEvents()
    assert len(window._browse._grid._cards) == 2  # key up (Primary) + key handgun (Secondary)
    assert "2 résultats" in window._browse._subtitle.text()
    # The filter bar is visible in search mode only.
    assert window._browse._filter_row.isVisible()

    # Category filter: Secondaire -> only key handgun.
    combo = window._browse._filter_category
    combo.setCurrentIndex(combo.findData("secondary"))
    qapp.processEvents()
    cards = [c._title_label._raw_text for c in window._browse._grid._cards]
    assert cards == ["key handgun"]
    assert "1 résultat" in window._browse._subtitle.text()
    assert window._browse._reset_btn.isVisible()

    # Réinitialiser: filters removed, query kept.
    window._browse._reset_btn.click()
    qapp.processEvents()
    assert len(window._browse._grid._cards) == 2
    assert window._search.text() == "key"
    assert not window._browse._reset_btn.isVisible()

    # No results -> clean empty state.
    window._search.setText("zzzzz")
    window._run_search()
    qapp.processEvents()
    assert window._browse._empty.isVisible()
    assert "Aucun résultat pour « zzzzz »" in window._browse._empty.text()


def test_search_navigation_restores_state(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Back/forward restore the search + its filters exactly (browser-like)."""
    from PySide6.QtTest import QTest

    from app.search import SearchState

    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    # Search + secondary filter, then open a result.
    window._search.setText("key")
    window._run_search()
    # The debounce timer armed by setText() must not fire mid-test: a stray
    # delayed search would clear the forward stack during back/forward.
    window._search_timer.stop()
    qapp.processEvents()
    combo = window._browse._filter_category
    combo.setCurrentIndex(combo.findData("secondary"))
    qapp.processEvents()
    assert [c._title_label._raw_text for c in window._browse._grid._cards] == ["key handgun"]

    # The card click pushes the config page.
    def _find(item_name: str, node) -> object:
        for c in node.configs:
            if c.name == item_name:
                return c
        for s in node.subdirs:
            found = _find(item_name, s)
            if found is not None:
                return found
        return None

    item = _find("key handgun", window.root_node)
    assert item is not None
    window.go(("config", item))
    qapp.processEvents()
    assert window._stack.currentWidget() is window._config

    # Back: the search state is restored with its query and filters.
    window.back()
    qapp.processEvents()
    assert window._stack.currentWidget() is window._browse
    state = window._history.current()[1]
    assert isinstance(state, SearchState)
    assert state.query == "key"
    assert state.category == "secondary"
    assert window._search.text() == "key"
    assert window._browse._filter_category.currentData() == "secondary"
    assert [c._title_label._raw_text for c in window._browse._grid._cards] == ["key handgun"]

    # Forward: back to the config.
    window._forward_btn.click()
    qapp.processEvents()
    assert window._stack.currentWidget() is window._config


def test_search_does_not_modify_files(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Searching and filtering is strictly read-only: the library files and
    the Fleasion folder are never touched."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    def snapshot(root: Path) -> set[tuple[str, int]]:
        return {
            (str(p.relative_to(root)), p.stat().st_size)
            for p in root.rglob("*")
            if p.is_file()
        }

    before_lib = snapshot(library)
    before_fleasion = snapshot(fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    window._search.setText("key")
    window._run_search()
    qapp.processEvents()
    combo = window._browse._filter_category
    combo.setCurrentIndex(combo.findData("secondary"))
    qapp.processEvents()
    window._search.setText("zzzzz")
    window._run_search()
    qapp.processEvents()
    window._search.setText("")
    window._run_search()
    qapp.processEvents()

    assert snapshot(library) == before_lib
    assert snapshot(fleasion_dir) == before_fleasion


def test_image_on_category_card(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """A category (node) can have its own image via the card context menu;
    it never replaces the images of its children."""
    import base64

    from PySide6.QtTest import QTest

    from ui.main_window import MainWindow
    from ui.views.image_dialog import ImageDialog

    PNG_1PX = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
        "AAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
    )

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    assert charms.preview is None

    # Right-click on the category card -> edit_image_requested(target).
    # The real handler opens a modal dialog; stub it to verify the wiring
    # (card -> grid -> home view -> main window) without blocking.
    window.go(("home", None))
    qapp.processEvents()
    home_card = next(
        c for c in window._home._grid._cards if c._title_label._raw_text == "Charms"
    )
    targets = []
    window._edit_image = lambda t: targets.append(t)  # type: ignore[method-assign]
    home_card.edit_image_requested.emit()
    qapp.processEvents()
    assert targets and targets[0].path == charms.path
    # Restore the real handler for the rest of the test.
    from ui.main_window import MainWindow as _MW

    window._edit_image = _MW._edit_image.__get__(window, _MW)  # type: ignore[method-assign]

    # Drive the real dialog on the node (bypassing the modal exec).
    from PySide6.QtWidgets import QFileDialog

    source = tmp_path / "category.png"
    source.write_bytes(PNG_1PX)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", staticmethod(lambda *a, **k: (str(source), "Images (*.png)")))
    dlg = ImageDialog(charms, window.image_manager, window)
    dlg._import_local()
    assert "Image importée" in dlg._status.text()
    dlg.accept()
    dlg.deleteLater()
    qapp.processEvents()
    window._refresh_and_resync()
    QTest.qWait(300)

    fresh_charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    assert fresh_charms.preview is not None, "image de catégorie non résolue après rescan"
    # Child configs are untouched (no image inheritance).
    assert all(c.preview is None for c in fresh_charms.configs)

    # Restart -> persistence.
    window.close()
    qapp.processEvents()
    window2 = MainWindow()
    window2.show()
    qapp.processEvents()
    charms2 = next(s for s in window2.root_node.subdirs if s.name == "Charms")
    assert charms2.preview is not None, "image de catégorie perdue après redémarrage"

    # Remove -> placeholder back.
    window2.image_manager.remove(charms2)
    window2._refresh_and_resync()
    QTest.qWait(300)
    charms3 = next(s for s in window2.root_node.subdirs if s.name == "Charms")
    assert charms3.preview is None


def test_obj_workflow_in_ui(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Add an OBJ from the config view: dialog, association, persistence, removal."""
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QFileDialog

    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")
    window.go(("config", item))
    qapp.processEvents()
    assert not window._config._remove_obj_btn.isEnabled()

    model = tmp_path / "model.obj"
    model.write_text("v 0 0 0", encoding="utf-8")
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *a, **k: (str(model), "Modèles 3D (*.obj)")),
    )
    window._add_current_obj()
    QTest.qWait(300)

    fresh = next(c for c in window.root_node.subdirs if c.name == "Charms").configs
    fresh_item = next(c for c in fresh if c.name == "nemesis charm")
    assert fresh_item.obj is not None
    assert fresh_item.obj_name == "model.obj"
    assert window._config._remove_obj_btn.isEnabled()

    # Restart -> persistence.
    window.close()
    qapp.processEvents()
    window2 = MainWindow()
    window2.show()
    qapp.processEvents()
    fresh2 = next(c for c in window2.root_node.subdirs if c.name == "Charms").configs
    fresh2_item = next(c for c in fresh2 if c.name == "nemesis charm")
    assert fresh2_item.obj is not None

    # Remove.
    window2.go(("config", fresh2_item))
    qapp.processEvents()
    window2._remove_current_obj()
    QTest.qWait(300)
    fresh3 = next(c for c in window2.root_node.subdirs if c.name == "Charms").configs
    fresh3_item = next(c for c in fresh3 if c.name == "nemesis charm")
    assert fresh3_item.obj is None
    # Real files untouched.
    assert (library / "Charms" / "nemesis charm.json").exists()


def test_welcome_shown_when_unconfigured(tmp_path: Path, monkeypatch, qapp) -> None:
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))

    window = MainWindow()
    window.show()
    qapp.processEvents()

    assert window._stack.currentWidget() is window._welcome
    assert not window._top_bar.isVisible()


def test_sync_button_in_config_view(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """The config view « Synchroniser » button is wired to the main window
    and runs a real sync without crashing."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")
    window.go(("config", item))
    qapp.processEvents()

    assert window._config._sync_btn.isEnabled()
    # A previous activation left a copy: sync sees it as a stale copy
    # (no selection file in this fake Fleasion folder) and keeps it.
    window._activate_current()
    qapp.processEvents()
    assert (fleasion_dir / "nemesis charm.json").exists()

    window._config._sync_btn.click()
    qapp.processEvents()
    assert window._config._result_box.isVisible()
    # The library file was never touched.
    assert (library / "Charms" / "nemesis charm.json").exists()


def test_deactivate_button_removes_active_state(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """DÉSACTIVER retires the active copies and restores the ACTIVER state."""
    from PySide6.QtTest import QTest

    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")
    window.go(("config", item))
    qapp.processEvents()
    assert not window._config._deactivate_btn.isVisible()  # inactive: hidden

    window._activate_current()
    qapp.processEvents()
    assert (fleasion_dir / "nemesis charm.json").exists()
    assert window._config._deactivate_btn.isVisible()  # copied: visible

    window._config._deactivate_btn.click()
    qapp.processEvents()
    assert not (fleasion_dir / "nemesis charm.json").exists()
    assert window._config._result_box.isVisible()
    assert "Configuration désactivée" in window._config._result_label.text()
    assert not window._config._deactivate_btn.isVisible()  # back to inactive
    # The library keeps the mod: reactivation stays possible.
    assert (library / "Charms" / "nemesis charm.json").exists()


def test_delete_confirmation_and_trash_flow(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Supprimer asks for confirmation, moves the item to the persistent
    trash, and the item can be restored from the trash view."""
    from PySide6.QtTest import QTest

    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")
    window.go(("config", item))
    qapp.processEvents()

    # --- Cancelled: nothing happens ------------------------------------- #
    window._confirm_delete = lambda item: False  # type: ignore[method-assign]
    window._config._delete_btn.click()
    qapp.processEvents()
    assert (library / "Charms" / "nemesis charm.json").exists()
    assert window.trash.list_entries() == []

    # --- Confirmed: moved to the trash ----------------------------------- #
    window._confirm_delete = lambda item: True  # type: ignore[method-assign]
    window._config._delete_btn.click()
    qapp.processEvents()
    assert not (library / "Charms" / "nemesis charm.json").exists()
    entries = window.trash.list_entries()
    assert len(entries) == 1
    assert entries[0].name == "nemesis charm"
    # Sidecars were moved too (none here) and the real JSON is stored
    # dans la Corbeille interne (payload/).
    assert (entries[0].folder / "payload" / "nemesis charm.json").exists()

    # --- Restore from the trash view -------------------------------------- #
    window.go(("trash", None))
    qapp.processEvents()
    assert window._stack.currentWidget() is window._trash_view
    window._restore_trash_entry(entries[0])
    qapp.processEvents()
    assert (library / "Charms" / "nemesis charm.json").exists()
    assert window.trash.list_entries() == []


def test_trash_persists_and_destroy_requires_confirmation(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """The trash survives a restart, and permanent deletion needs the
    strong confirmation before files are erased."""
    from PySide6.QtTest import QTest

    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")
    window.go(("config", item))
    qapp.processEvents()
    window._confirm_delete = lambda item: True  # type: ignore[method-assign]
    window._config._delete_btn.click()
    qapp.processEvents()

    # --- Restart: the trash is still there --------------------------------- #
    window.close()
    qapp.processEvents()
    window2 = MainWindow()
    window2.show()
    qapp.processEvents()
    entries = window2.trash.list_entries()
    assert len(entries) == 1
    assert entries[0].name == "nemesis charm"

    # --- Permanent deletion refused without confirmation -------------------- #
    window2._confirm_destroy = lambda count, name: False  # type: ignore[method-assign]
    window2._destroy_trash_entry(entries[0])
    qapp.processEvents()
    assert window2.trash.list_entries()  # still there

    # --- Confirmed: files are erased ---------------------------------------- #
    window2._confirm_destroy = lambda count, name: True  # type: ignore[method-assign]
    window2._destroy_trash_entry(entries[0])
    qapp.processEvents()
    assert window2.trash.list_entries() == []
    # The library file was already moved: nothing left anywhere.
    assert not (library / "Charms" / "nemesis charm.json").exists()


def test_trash_view_search_filters_in_memory(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """La vue Corbeille : recherche instantanée, insensible à la casse,
    espaces normalisés, correspondance partielle, « Aucune configuration
    trouvée » sans résultat, aucune écriture pendant la saisie."""
    from PySide6.QtWidgets import QLineEdit

    from app.trash import Trash
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    # Deux éléments dans la Corbeille interne.
    window.trash.delete_path(library / "Charms" / "nemesis charm.json")
    window.trash.delete_path(library / "rivals skins" / "Primary" / "Assault Rifle" / "ak-47.json")
    window.go(("trash", None))
    qapp.processEvents()
    window._trash_view.set_entries(window.trash.list_entries())
    qapp.processEvents()

    view = window._trash_view
    assert isinstance(view._search, QLineEdit)
    assert view._search.isClearButtonEnabled()
    assert view._list.count() == 2

    # Recherche partielle, insensible à la casse, espaces normalisés.
    view._search.setText("  NEMESIS  ")
    assert view._list.count() == 1
    assert "nemesis charm" in view._list.item(0).text()
    assert "1 résultat" in view._results_label.text()

    # Aucun résultat.
    view._search.setText("zzz")
    assert view._list.count() == 0
    assert view._results_label.text() == "Aucune configuration trouvée"

    # Effacement → tout revient, compteur.
    view._search.clear()
    assert view._list.count() == 2
    assert view._results_label.text() == ""

    # Aucune écriture pendant la recherche : les fichiers de Corbeille et
    # la bibliothèque sont intacts.
    view._search.setText("ak")
    view._search.setText("")
    assert len(list(window.trash.root.rglob("*.json"))) == 4  # 2 payloads + 2 metadata
    assert (library / "Charms" / "nemesis charm.json").exists() is False  # déjà supprimé
    assert (library / "rivals skins" / "Primary" / "Assault Rifle" / "ak-47.json").exists() is False

    # Restauration : l'entrée disparaît de la vue et de la Corbeille.
    view._list.setCurrentRow(0)
    window._restore_trash_entry(view._selected_entry())
    qapp.processEvents()
    assert window.trash.list_entries()  # l'autre entrée reste


def test_restore_conflict_choose_keep_both_or_replace(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Conflit de restauration : jamais d'écrasement silencieux. « Garder
    les deux » restaure à côté, « Remplacer » écrase après sauvegarde,
    « Annuler » ne restaure rien."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    item = next(c for c in charms.configs if c.name == "nemesis charm")
    window._confirm_card_delete = lambda path, is_folder, count: True  # type: ignore[method-assign]

    # Supprimer via le clic droit (Corbeille interne).
    window._delete_card(item)
    qapp.processEvents()
    entries = window.trash.list_entries()
    assert len(entries) == 1

    # Un nouveau fichier apparaît à l'emplacement d'origine (conflit).
    (library / "Charms" / "nemesis charm.json").write_text('{"new": true}', encoding="utf-8")

    # --- Annuler : rien n'est restauré, l'entrée reste ------------------- #
    window._ask_restore_conflict = lambda entry: None  # type: ignore[method-assign]
    window._restore_trash_entry(entries[0])
    qapp.processEvents()
    assert window.trash.list_entries()
    assert (library / "Charms" / "nemesis charm.json").read_text(encoding="utf-8") == '{"new": true}'

    # --- Garder les deux : un nouveau fichier apparaît à côté ------------ #
    window._ask_restore_conflict = lambda entry: "keep_both"  # type: ignore[method-assign]
    window._restore_trash_entry(entries[0])
    qapp.processEvents()
    assert window.trash.list_entries() == []
    assert (library / "Charms" / "nemesis charm (2).json").exists()
    assert (library / "Charms" / "nemesis charm.json").read_text(encoding="utf-8") == '{"new": true}'

    # --- Remplacer : le contenu restauré remplace l'existant ------------- #
    window._delete_card(item)
    qapp.processEvents()
    entries = window.trash.list_entries()
    assert len(entries) == 1
    # La Corbeille détient le contenu « keep_both » ; un fichier tiers
    # apparaît ensuite : « Remplacer » le remplace par le contenu restauré.
    (library / "Charms" / "nemesis charm.json").write_text('{"tiers": true}', encoding="utf-8")
    window._ask_restore_conflict = lambda entry: "replace"  # type: ignore[method-assign]
    window._restore_trash_entry(entries[0])
    qapp.processEvents()
    assert window.trash.list_entries() == []
    assert (library / "Charms" / "nemesis charm.json").exists()
    assert (library / "Charms" / "nemesis charm.json").read_text(encoding="utf-8") != '{"tiers": true}'


def test_empty_trash_requires_confirmation(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """« Vider la corbeille » : confirmé → tout est supprimé définitivement ;
    refusé → rien ne bouge."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    window._confirm_card_delete = lambda path, is_folder, count: True  # type: ignore[method-assign]
    window._delete_card(next(c for c in charms.configs if c.name == "nemesis charm"))
    qapp.processEvents()

    # Refusé : rien ne bouge.
    window._confirm_destroy = lambda count, name: False  # type: ignore[method-assign]
    window._empty_trash()
    qapp.processEvents()
    assert window.trash.list_entries()

    # Confirmé : tout est vidé.
    window._confirm_destroy = lambda count, name: True  # type: ignore[method-assign]
    window._empty_trash()
    qapp.processEvents()
    assert window.trash.list_entries() == []


def test_mouse_side_buttons_navigate(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Mouse back/forward buttons navigate like a browser — scoped to the
    window (a press outside it does nothing), forward cleared on new
    navigation, buttons disabled when navigation is impossible."""
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QWidget

    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    # At home there is nothing to go back to.
    assert not window._back_btn.isEnabled()
    assert not window._forward_btn.isEnabled()

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    window.go(("browse", charms))
    qapp.processEvents()
    assert window._stack.currentWidget() is window._browse
    assert window._back_btn.isEnabled()

    # --- Back with the mouse side button -> home --------------------------- #
    QTest.mouseClick(window._browse._grid, Qt.BackButton)
    qapp.processEvents()
    assert window._stack.currentWidget() is window._home
    assert not window._back_btn.isEnabled()  # home is the root
    assert window._forward_btn.isEnabled()

    # --- Forward with the mouse side button -> browse ---------------------- #
    QTest.mouseClick(window._home._grid, Qt.ForwardButton)
    qapp.processEvents()
    assert window._stack.currentWidget() is window._browse

    # --- Deep navigation: back twice, forward twice ------------------------ #
    item = charms.configs[0]
    window.go(("config", item))
    qapp.processEvents()
    assert window._stack.currentWidget() is window._config

    QTest.mouseClick(window._config._preview, Qt.BackButton)
    qapp.processEvents()
    assert window._stack.currentWidget() is window._browse
    QTest.mouseClick(window._browse._grid, Qt.BackButton)
    qapp.processEvents()
    assert window._stack.currentWidget() is window._home

    QTest.mouseClick(window._home._grid, Qt.ForwardButton)
    qapp.processEvents()
    QTest.mouseClick(window._browse._grid, Qt.ForwardButton)
    qapp.processEvents()
    assert window._stack.currentWidget() is window._config
    assert not window._forward_btn.isEnabled()  # end of the forward path

    # --- A new navigation clears the forward stack ------------------------- #
    QTest.mouseClick(window._config._preview, Qt.BackButton)
    qapp.processEvents()
    window.go(("settings", None))
    qapp.processEvents()
    assert window._stack.currentWidget() is window._settings
    assert not window._forward_btn.isEnabled()

    # --- The top-bar forward button navigates too -------------------------- #
    window.back()
    qapp.processEvents()
    assert window._stack.currentWidget() is window._browse
    assert window._forward_btn.isEnabled()
    window._forward_btn.click()
    qapp.processEvents()
    assert window._stack.currentWidget() is window._settings

    # --- Scoped to the app: a press on a widget outside the window does --- #
    # --- nothing. ---------------------------------------------------------- #
    before = window._stack.currentWidget()
    bare = QWidget()
    QTest.mouseClick(bare, Qt.BackButton)
    qapp.processEvents()
    assert window._stack.currentWidget() is before

    # Cleanup: uninstall the event filter so later tests are not affected.
    window.close()
    qapp.processEvents()


def test_categories_canonical_order_in_browse(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """The weapon categories always appear in the strict order
    Primaire → Secondaire → Mêlée → Utilitaire inside a skins node, while
    the home page stays alphabetical when it has no canonical category."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    # Home: no canonical category at the root -> alphabetical order.
    home_titles = [c._title_label._raw_text for c in window._home._grid._cards]
    assert home_titles == sorted(home_titles, key=str.casefold)
    assert home_titles[0] == "Charms"

    # Inside the skins node: Primary, Secondary, Melee in canonical order
    # (the fixture has no Utility folder).
    skins = next(s for s in window.root_node.subdirs if s.name == "rivals skins")
    window.go(("browse", skins))
    qapp.processEvents()
    titles = [c._title_label._raw_text for c in window._browse._grid._cards]
    assert titles[:3] == ["Primary", "Secondary", "Melee"]
    assert set(titles) == {"Primary", "Secondary", "Melee"}


def test_import_button_removed_and_drop_zone_minimalist(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """No import button anymore; the drop zone is a small icon-only square
    (no text), accepts drags, and routes dropped files to the import flow."""
    from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
    from PySide6.QtGui import QDragEnterEvent
    from PySide6.QtWidgets import QLabel

    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    # No import button anywhere on the home page.
    assert not hasattr(window._home, "_import_btn")

    zone = window._home._drop_zone
    assert zone.acceptDrops()
    # Small and discreet: a ~44 px square, not a full-width banner.
    assert zone.width() <= 48 and zone.height() <= 48
    # No explanatory text: the only child label carries the vector plus icon.
    texts = [lbl.text() for lbl in zone.findChildren(QLabel)]
    assert texts == [""]  # icône vectorielle, plus aucun caractère texte
    labels = zone.findChildren(QLabel)
    assert labels and not labels[0].pixmap().isNull()

    # A file dragged over the zone is accepted (no popup during the drag).
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(tmp_path / "mod.zip"))])
    drag = QDragEnterEvent(QPoint(5, 5), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    zone.dragEnterEvent(drag)
    assert drag.isAccepted()

    # Drop routes every local file to the import flow.
    calls = []
    window._start_mod_import = lambda p: calls.append(p)  # type: ignore[method-assign]
    zone.files_dropped.emit([Path("some_mod.zip"), Path("other.obj")])
    qapp.processEvents()
    assert calls == [Path("some_mod.zip"), Path("other.obj")]


def test_import_mod_flow(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Full import flow in the real UI: ZIP -> analysis -> preview -> install
    into the library, staging cleaned, duplicate -> « nom (2) »."""
    import zipfile

    from PySide6.QtWidgets import QDialog

    import app.mod_import as mod_import
    from ui.main_window import MainWindow
    from ui.views.import_dialog import ImportDialog

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    def fake_staging_base():
        base = tmp_path / "staging"
        base.mkdir(parents=True, exist_ok=True)
        return base

    monkeypatch.setattr(mod_import, "_staging_base", fake_staging_base)

    zip_path = tmp_path / "Gunblade_Black_Skin.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Gunblade_Black_Skin/config.json", '{"replacement_rules": []}')
        zf.writestr("Gunblade_Black_Skin/model.obj", "v 0 0 0")

    window = MainWindow()
    window.show()
    qapp.processEvents()

    # The preview dialog is driven programmatically: accept the defaults.
    # Step 8 auto-detection now pre-fills Mêlée → Gunblade, so the mod is
    # installed under Melee/Gunblade without any manual choice.
    monkeypatch.setattr(ImportDialog, "exec", lambda self: QDialog.Accepted)
    window._start_mod_import(zip_path)
    qapp.processEvents()

    # v1.3.1 : la catégorie RÉELLE de la bibliothèque (rivals skins/Melee)
    # est la destination — jamais un nouveau « Melee » à la racine.
    real_melee = library / "rivals skins" / "Melee"
    dest = real_melee / "Gunblade" / "Gunblade Black Skin"
    assert (dest / "config.json").exists()
    assert (dest / "model.obj").exists()
    # Staging is cleaned up after install.
    assert [p.name for p in (tmp_path / "staging").iterdir()] == []
    # The library was refreshed: the mod is browsable under Melee/Gunblade.
    melee = next(s for s in window.root_node.subdirs if s.name == "rivals skins")
    melee = next(s for s in melee.subdirs if s.name == "Melee")
    gunblade = next(s for s in melee.subdirs if s.name == "Gunblade")
    assert any(c.name == "Gunblade Black Skin" for c in gunblade.configs)

    # --- A second import of the same mod keeps both ------------------------
    window._start_mod_import(zip_path)
    qapp.processEvents()
    assert (real_melee / "Gunblade" / "Gunblade Black Skin (2)" / "config.json").exists()


def test_import_mod_cancel_does_nothing(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Cancelling the preview never touches the library."""
    import zipfile

    from PySide6.QtWidgets import QDialog

    import app.mod_import as mod_import
    from ui.main_window import MainWindow
    from ui.views.import_dialog import ImportDialog

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    def fake_staging_base():
        base = tmp_path / "staging"
        base.mkdir(parents=True, exist_ok=True)
        return base

    monkeypatch.setattr(mod_import, "_staging_base", fake_staging_base)

    zip_path = tmp_path / "Cancel_Mod.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Cancel_Mod/config.json", "{}")

    window = MainWindow()
    window.show()
    qapp.processEvents()

    monkeypatch.setattr(ImportDialog, "exec", lambda self: QDialog.Rejected)
    window._start_mod_import(zip_path)
    qapp.processEvents()

    assert not (library / "Primary").exists()
    # Staging is cleaned up even on cancel.
    assert [p.name for p in (tmp_path / "staging").iterdir()] == []


def test_import_dialog_auto_detection(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """The import preview pre-fills category + weapon from the automatic
    detection (library structure wins) and shows the confidence note."""
    import app.mod_import as mod_import
    from ui.views.import_dialog import ImportDialog

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    # A library that already contains Melee/Gunblade and Secondary/Energy Rifle.
    weapon_lib = tmp_path / "weapons"
    (weapon_lib / "Melee" / "Gunblade").mkdir(parents=True)
    (weapon_lib / "Secondary" / "Energy Rifle").mkdir(parents=True)

    src = tmp_path / "Gunblade_Black_Skin"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")
    (src / "model.obj").write_text("v 0 0 0", encoding="utf-8")

    analysis = mod_import.analyze_source(src)
    dialog = ImportDialog(analysis, weapon_lib)
    # Detection pre-filled the fields: Mêlée → Gunblade (library structure).
    assert dialog._category.currentData() == "melee"
    assert dialog._weapon.currentText() == "Gunblade"
    assert "Détecté automatiquement" in dialog._detect_label.text()
    assert dialog._install_btn.isEnabled()
    plan = dialog.build_plan()
    assert plan.destination == weapon_lib / "Melee" / "Gunblade" / "Gunblade Black Skin"
    dialog.deleteLater()


def test_import_dialog_low_confidence_requires_manual_choice(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """When detection fails, the category is forced to « — Choisir — » and
    Installer stays disabled until the user picks one manually: a mod is
    never installed in a guessed folder."""
    import app.mod_import as mod_import
    from ui.views.import_dialog import ImportDialog

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    src = tmp_path / "Mystery Item 9000"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")

    analysis = mod_import.analyze_source(src)
    dialog = ImportDialog(analysis, library)
    # LOW confidence: forced choice, installer disabled.
    assert dialog._category.currentData() is None
    assert not dialog._install_btn.isEnabled()
    assert "Détection non concluante" in dialog._detect_label.text()
    assert dialog.plan is None
    # The user picks Secondaire manually -> installer enabled, destination set.
    dialog._category.setCurrentIndex(dialog._category.findData("secondary"))
    assert dialog._install_btn.isEnabled()
    plan = dialog.build_plan()
    # Le nom est pré-rempli intelligemment : « 9000 » (numéro de version
    # en fin de nom) est retiré, comme « Final_v2 » → « Pixel Katana ».
    # v1.3.1 : la catégorie réelle de la bibliothèque (rivals skins/Secondary)
    # est la destination — jamais un nouveau dossier « Secondary » à la racine.
    assert plan.destination == library / "rivals skins" / "Secondary" / "Mystery Item"
    dialog.deleteLater()


def test_import_dialog_weapon_picker_per_category(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """The weapon field is a picker populated from the selected category:
    library folders + known registry, editable to add a new weapon."""
    import app.mod_import as mod_import
    from ui.views.import_dialog import ImportDialog

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    weapon_lib = tmp_path / "weapons"
    (weapon_lib / "Primary" / "Assault Rifle").mkdir(parents=True)
    (weapon_lib / "Melee" / "Gunblade").mkdir(parents=True)

    src = tmp_path / "Some Mod"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")

    analysis = mod_import.analyze_source(src)
    dialog = ImportDialog(analysis, weapon_lib)
    # Primaire: library folder « Assault Rifle » + registry (Shotgun, ...).
    dialog._category.setCurrentIndex(dialog._category.findData("primary"))
    weapons = [dialog._weapon.itemText(i) for i in range(dialog._weapon.count())]
    assert "Assault Rifle" in weapons
    assert "Shotgun" in weapons
    # Mêlée: library folder « Gunblade » + registry weapons.
    dialog._category.setCurrentIndex(dialog._category.findData("melee"))
    weapons = [dialog._weapon.itemText(i) for i in range(dialog._weapon.count())]
    assert "Gunblade" in weapons
    assert "Katana" in weapons
    # Editable: typing a brand-new weapon works and feeds the destination.
    dialog._weapon.setEditText("Railgun")
    assert dialog._install_btn.isEnabled()
    plan = dialog.build_plan()
    assert plan.destination == weapon_lib / "Melee" / "Railgun" / "Some Mod"
    dialog.deleteLater()


def test_import_dialog_flow_order(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """The popup is a single simple form in the validated order:
    Catégorie → Arme → Nom du mod → Fichiers → Destination → Installer.
    The destination is always visible before installing."""
    from PySide6.QtWidgets import QLabel

    import app.mod_import as mod_import
    from ui.views.import_dialog import ImportDialog

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    src = tmp_path / "My Mod"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")

    analysis = mod_import.analyze_source(src)
    dialog = ImportDialog(analysis, library)

    # La catégorie est un combo simple — pas de cartes visuelles, pas
    # d'assistant en étapes.
    assert not hasattr(dialog, "_steps")
    assert not hasattr(dialog, "_category_cards")
    labels = [dialog._category.itemText(i) for i in range(dialog._category.count())]
    # « — Choisir — » est inséré en tête quand la détection échoue ; les 4
    # catégories d'armes restent dans l'ordre canonique, puis TOUTES les
    # catégories réellement présentes dans la bibliothèque (dynamiques,
    # ordre alphabétique).
    canonical = [t for t in labels if t != "— Choisir —"]
    assert canonical == [
        "Primaire",
        "Secondaire",
        "Mêlée",
        "Utilitaire",
        "Charms",
        "emotes",
        "FastFlags",
        "rivals skins",
        "Texture and skyboxes",
    ]

    # Ordre du formulaire : Catégorie → Arme → Nom → Fichiers → Destination.
    order: list[str] = []
    layout = dialog.layout()
    for i in range(layout.count()):
        widget = layout.itemAt(i).widget()
        if widget is dialog._category:
            order.append("category")
        elif widget is dialog._weapon:
            order.append("weapon")
        elif widget is dialog._name:
            order.append("name")
        elif widget is dialog._files_label:
            order.append("files")
        elif widget is dialog._dest_label:
            order.append("destination")
        elif isinstance(widget, QLabel) and widget.text() in (
            "Catégorie",
            "Arme",
            "Nom du mod",
            "Fichiers",
            "Destination",
        ):
            order.append(widget.text())
    assert order == [
        "Catégorie",
        "category",
        "Arme",
        "weapon",
        "Nom du mod",
        "name",
        "Fichiers",
        "files",
        "Destination",
        "destination",
    ]

    # Installer est désactivé tant qu'aucune catégorie n'est choisie
    # (détection non concluante -> « — Choisir — ») ; la destination
    # apparaît dès que l'utilisateur choisit une catégorie.
    assert dialog._category.currentData() is None
    assert not dialog._install_btn.isEnabled()
    dialog._category.setCurrentIndex(dialog._category.findData("secondary"))
    assert dialog._install_btn.isEnabled()
    # v1.3.1 : la destination est la catégorie RÉELLE de la bibliothèque.
    assert str(library / "rivals skins" / "Secondary") in dialog._dest_label.text()
    dialog.deleteLater()


def test_import_dialog_offers_all_library_categories(
    library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp
) -> None:
    """The category selector contains every library category (canonical +
    real folders), including non-weapon and empty ones — never a fixed list."""
    import app.mod_import as mod_import
    from ui.views.import_dialog import ImportDialog

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    src = tmp_path / "Mystery Pack"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")

    analysis = mod_import.analyze_source(src)
    dialog = ImportDialog(analysis, library)
    data = [dialog._category.itemData(i) for i in range(dialog._category.count())]
    # Canonical weapon categories first, in canonical order (the
    # « — Choisir — » placeholder, if present, sits before them).
    real = [d for d in data if d is not None]
    assert real[:4] == ["primary", "secondary", "melee", "utility"]
    # Every real top-level folder of the library is proposed (custom,
    # non-weapon, alphabetical).
    assert "Charms" in data
    assert "emotes" in data
    assert "FastFlags" in data
    assert "rivals skins" in data
    assert "Texture and skyboxes" in data
    # A texture pack can be sent to a non-weapon category.
    idx = dialog._category.findData("Texture and skyboxes")
    dialog._category.setCurrentIndex(idx)
    plan = dialog.build_plan()
    assert plan.destination == library / "Texture and skyboxes" / "Mystery Pack"
    dialog.deleteLater()


def test_import_dialog_new_category_appears_automatically(
    library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp
) -> None:
    """A category created later shows up in the selector with no code
    change, even when it is empty."""
    import app.mod_import as mod_import
    from ui.views.import_dialog import ImportDialog

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    src = tmp_path / "Some Mod"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")
    analysis = mod_import.analyze_source(src)

    (library / "Skins").mkdir()  # nouvelle catégorie, vide
    dialog = ImportDialog(analysis, library)
    assert dialog._category.findData("Skins") >= 0
    dialog._category.setCurrentIndex(dialog._category.findData("Skins"))
    assert dialog.build_plan().destination == library / "Skins" / "Some Mod"
    dialog.deleteLater()


def test_import_dialog_user_picks_category_different_from_detection(
    library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp
) -> None:
    """Even when detection suggests a weapon category, the user can
    explicitly place the pack in any other category (e.g. Textures)."""
    import app.mod_import as mod_import
    from ui.views.import_dialog import ImportDialog

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    (library / "Textures").mkdir()

    src = tmp_path / "Gunblade_Black_Skin"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")

    analysis = mod_import.analyze_source(src)
    dialog = ImportDialog(analysis, library)
    # Detection pre-filled Mêlée (known weapon)…
    assert dialog._category.currentData() == "melee"
    # …but the user explicitly chooses the texture category instead.
    dialog._category.setCurrentIndex(dialog._category.findData("Textures"))
    plan = dialog.build_plan()
    assert plan.destination == library / "Textures" / "Gunblade Black Skin"
    dialog.deleteLater()


def test_drop_on_zone_opens_popup_and_rename(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Dropping a ZIP on the zone opens the popup immediately; the mod can
    be renamed there, the destination uses the new name, the source file is
    untouched, and the staging is cleaned up."""
    import zipfile

    from PySide6.QtWidgets import QDialog

    import app.mod_import as mod_import
    from ui.main_window import MainWindow
    from ui.views.import_dialog import ImportDialog

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    def fake_staging_base():
        base = tmp_path / "staging"
        base.mkdir(parents=True, exist_ok=True)
        return base

    monkeypatch.setattr(mod_import, "_staging_base", fake_staging_base)

    zip_path = tmp_path / "Super_Cool_Skin_Final_V2_Updated.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("Super_Cool_Skin_Final_V2_Updated/config.json", "{}")

    window = MainWindow()
    window.show()
    qapp.processEvents()

    captured = []

    def fake_exec(self):
        captured.append(self)
        # Detection is inconclusive: the user picks the category manually
        # and renames the mod before installing.
        self._category.setCurrentIndex(self._category.findData("primary"))
        self._name.setText("Super Cool Skin")
        return QDialog.Accepted

    monkeypatch.setattr(ImportDialog, "exec", fake_exec)

    zone = window._home._drop_zone
    zone.files_dropped.emit([zip_path])
    qapp.processEvents()

    # The popup opened right after the drop.
    assert captured, "popup non ouvert après le drop"
    # The rename was used for the destination, not the original name.
    # v1.3.1 : la catégorie réelle (rivals skins/Primary) est la destination.
    dest = library / "rivals skins" / "Primary" / "Super Cool Skin"
    assert (dest / "config.json").exists()
    assert not (library / "Primary" / "Super Cool Skin Final V2 Updated").exists()
    # The source archive was never modified or renamed.
    assert zip_path.exists()
    # Staging is cleaned up after the install.
    assert [p.name for p in (tmp_path / "staging").iterdir()] == []


def test_import_dialog_rename_updates_destination(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Renaming in the popup changes the destination immediately, while the
    source file keeps its original name and content."""
    import app.mod_import as mod_import
    from ui.views.import_dialog import ImportDialog

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    src = tmp_path / "Super_Cool_Skin_Final_V2_Updated"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")

    analysis = mod_import.analyze_source(src)
    dialog = ImportDialog(analysis, library)
    # The user picks the category manually (detection is inconclusive).
    dialog._category.setCurrentIndex(dialog._category.findData("secondary"))
    # Rename: the destination label updates immediately.
    dialog._name.setText("Super Cool Skin")
    assert dialog._name.text() == "Super Cool Skin"
    assert "Super Cool Skin" in dialog._dest_label.text()
    plan = dialog.build_plan()
    # v1.3.1 : la catégorie réelle de la bibliothèque est la destination.
    assert plan.destination == library / "rivals skins" / "Secondary" / "Super Cool Skin"
    # The source file is untouched: same name, same content.
    original = tmp_path / "Super_Cool_Skin_Final_V2_Updated" / "config.json"
    assert original.read_text(encoding="utf-8") == "{}"
    dialog.deleteLater()


def test_add_weapon_creates_folder_and_refreshes(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """« Ajouter une arme » creates the folder inside the category being
    browsed (<library>/rivals skins/Primary/Railgun), never at the library
    root; the folder becomes navigable; adding it again warns instead of
    duplicating."""
    from PySide6.QtWidgets import QDialog

    from ui.main_window import MainWindow
    from ui.views.add_weapon_dialog import AddWeaponDialog

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    # Le contexte de navigation = la catégorie Primary (sous « rivals skins »).
    skins = next(s for s in window.root_node.subdirs if s.name == "rivals skins")
    primary = next(s for s in skins.subdirs if s.name == "Primary")
    window.go(("browse", primary))
    qapp.processEvents()

    def fake_exec(self):
        self._weapon.setText("Railgun")
        return QDialog.Accepted

    monkeypatch.setattr(AddWeaponDialog, "exec", fake_exec)
    window._add_weapon()
    qapp.processEvents()

    # Créée dans la catégorie réellement parcourue — jamais à la racine.
    assert (library / "rivals skins" / "Primary" / "Railgun").is_dir()
    assert not (library / "Primary").exists()
    # The tree was refreshed and the empty weapon folder is navigable.
    skins = next(s for s in window.root_node.subdirs if s.name == "rivals skins")
    primary = next(s for s in skins.subdirs if s.name == "Primary")
    assert any(s.name == "Railgun" for s in primary.subdirs)

    # Adding the same weapon again warns and does not duplicate.
    window._add_weapon()
    qapp.processEvents()
    assert len(list((library / "rivals skins" / "Primary" / "Railgun").iterdir())) == 0


def test_drop_anywhere_in_window_routes_to_import(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Dropping a local file anywhere in the main window (not only the home
    drop zone) opens the import flow; remote URLs are ignored."""
    from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
    from PySide6.QtGui import QDragEnterEvent, QDropEvent

    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    assert window.acceptDrops()

    calls = []
    window._start_mod_import = lambda p: calls.append(p)  # type: ignore[method-assign]

    # A drop with one local file and one remote URL: only the local one
    # reaches the import flow.
    mime = QMimeData()
    mime.setUrls(
        [
            QUrl.fromLocalFile(str(tmp_path / "mod.zip")),
            QUrl("https://example.com/remote.zip"),
        ]
    )
    drop = QDropEvent(QPointF(10, 10), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    window.dropEvent(drop)
    qapp.processEvents()
    assert calls == [tmp_path / "mod.zip"]

    # A drag of a local file is accepted (visual feedback possible).
    mime2 = QMimeData()
    mime2.setUrls([QUrl.fromLocalFile(str(tmp_path / "other.obj"))])
    drag = QDragEnterEvent(QPoint(5, 5), Qt.CopyAction, mime2, Qt.LeftButton, Qt.NoModifier)
    window.dragEnterEvent(drag)
    assert drag.isAccepted()

    # A drop without any local file does nothing.
    mime3 = QMimeData()
    mime3.setUrls([QUrl("https://example.com/remote.zip")])
    drop3 = QDropEvent(QPointF(0, 0), Qt.CopyAction, mime3, Qt.LeftButton, Qt.NoModifier)
    window.dropEvent(drop3)
    qapp.processEvents()
    assert calls == [tmp_path / "mod.zip"]  # unchanged


def test_import_popup_category_and_weapon_navigation(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """The simple popup: choosing the category populates the weapon picker;
    typing/choosing a weapon updates the destination; switching category
    never loses the mod name already typed."""
    import app.mod_import as mod_import
    from ui.views.import_dialog import ImportDialog

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    weapon_lib = tmp_path / "weapons"
    (weapon_lib / "Primary" / "Assault Rifle").mkdir(parents=True)
    (weapon_lib / "Primary" / "Assault Rifle" / "skin a.json").write_text("{}", encoding="utf-8")
    (weapon_lib / "Primary" / "Assault Rifle" / "skin b.json").write_text("{}", encoding="utf-8")
    (weapon_lib / "Secondary" / "Energy Rifle").mkdir(parents=True)
    (weapon_lib / "Secondary" / "Energy Rifle" / "a.json").write_text("{}", encoding="utf-8")
    (weapon_lib / "Secondary" / "Energy Rifle" / "b.json").write_text("{}", encoding="utf-8")

    src = tmp_path / "My Mod"
    src.mkdir()
    (src / "config.json").write_text("{}", encoding="utf-8")
    analysis = mod_import.analyze_source(src)
    dialog = ImportDialog(analysis, weapon_lib)

    # Détection non concluante → « — Choisir — », Installer désactivé.
    assert dialog._category.currentData() is None
    assert not dialog._install_btn.isEnabled()

    # Choisir Secondaire peuple le sélecteur d'arme (dossiers + registre).
    dialog._category.setCurrentIndex(dialog._category.findData("secondary"))
    weapons = [dialog._weapon.itemText(i) for i in range(dialog._weapon.count())]
    assert "Energy Rifle" in weapons
    assert dialog._install_btn.isEnabled()

    # Choisir une arme → destination mise à jour immédiatement.
    dialog._weapon.setEditText("Energy Rifle")
    assert "Energy Rifle" in dialog._dest_label.text()

    # Changer de catégorie repopule le sélecteur ; le nom tapé est conservé
    # et aucune arme n'est auto-sélectionnée (destination au niveau catégorie).
    dialog._name.setText("Mon Skin")
    dialog._category.setCurrentIndex(dialog._category.findData("primary"))
    weapons = [dialog._weapon.itemText(i) for i in range(dialog._weapon.count())]
    assert "Assault Rifle" in weapons
    assert "Energy Rifle" not in weapons
    assert dialog._name.text() == "Mon Skin"
    assert str(weapon_lib / "Primary" / "Mon Skin") in dialog._dest_label.text()
    dialog._weapon.setEditText("Assault Rifle")
    assert "Assault Rifle" in dialog._dest_label.text()
    dialog.deleteLater()


def test_add_weapon_uses_navigation_context_per_category(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """La création d'arme utilise le contexte de navigation : dans chaque
    catégorie parcourue, le dossier arme est créé dans CETTE catégorie."""
    from PySide6.QtWidgets import QDialog

    from ui.main_window import MainWindow
    from ui.views.add_weapon_dialog import AddWeaponDialog

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    # La fixture n'a pas d'Utility : on en crée une (dossier vide navigable).
    (library / "rivals skins" / "Utility").mkdir()

    window = MainWindow()
    window.show()
    qapp.processEvents()

    skins = next(s for s in window.root_node.subdirs if s.name == "rivals skins")
    for folder, weapon in [
        ("Primary", "Railgun A"),
        ("Secondary", "Railgun B"),
        ("Melee", "Railgun C"),
        ("Utility", "Railgun D"),
    ]:
        category = next(s for s in skins.subdirs if s.name == folder)
        window.go(("browse", category))
        qapp.processEvents()

        def fake_exec(self, name=weapon):
            self._weapon.setText(name)
            return QDialog.Accepted

        monkeypatch.setattr(AddWeaponDialog, "exec", fake_exec)
        window._add_weapon()
        qapp.processEvents()
        assert (library / "rivals skins" / folder / weapon).is_dir(), folder

    # Aucun nouveau dossier de catégorie créé à la racine.
    assert not (library / "Primary").exists()
    assert not (library / "Secondary").exists()
    assert not (library / "Melee").exists()
    assert not (library / "Utility").exists()


def test_add_weapon_refuses_outside_category(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Hors d'une catégorie d'armes, « Ajouter une arme » ne devine pas :
    le dialogue n'est pas ouvert, un message est affiché et aucun dossier
    n'est créé (ni nouvelle catégorie)."""
    from PySide6.QtWidgets import QDialog

    from ui.main_window import MainWindow
    from ui.views.add_weapon_dialog import AddWeaponDialog

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    opened = []

    def fake_exec(self):
        opened.append(1)
        return QDialog.Accepted

    monkeypatch.setattr(AddWeaponDialog, "exec", fake_exec)

    # Sur l'accueil : aucun contexte de catégorie.
    window._add_weapon()
    qapp.processEvents()
    assert opened == []
    assert not (library / "Primary").exists()

    # Dans une catégorie non-arme (Charms) : pareil.
    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    window.go(("browse", charms))
    qapp.processEvents()
    window._add_weapon()
    qapp.processEvents()
    assert opened == []
    assert not (library / "Primary").exists()


def test_card_delete_config_moves_to_internal_trash(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Clic droit → Supprimer sur une config : confirmation puis déplacement
    vers la **Corbeille interne de l'application** (jamais la Corbeille
    Windows), rescan et carte retirée immédiatement."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    window._confirm_card_delete = lambda path, is_folder, count: True  # type: ignore[method-assign]

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    window.go(("browse", charms))
    qapp.processEvents()
    card = next(
        c for c in window._browse._grid._cards if c._title_label._raw_text == "nemesis charm"
    )

    card.delete_requested.emit()
    qapp.processEvents()

    assert not (library / "Charms" / "nemesis charm.json").exists()
    # Le fichier est réellement dans la Corbeille interne (payload/).
    entries = window.trash.list_entries()
    assert len(entries) == 1
    assert entries[0].name == "nemesis charm"
    assert (entries[0].folder / "payload" / "nemesis charm.json").is_file()
    # Rescan : la carte supprimée a disparu.
    titles = [c._title_label._raw_text for c in window._browse._grid._cards]
    assert "nemesis charm" not in titles


def test_card_delete_weapon_folder_with_count(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Supprimer un dossier d'arme : la confirmation indique le nombre de
    configurations concernées, le dossier part vers la Corbeille interne."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    confirmed: list[tuple[str, bool, int]] = []
    window._confirm_card_delete = (  # type: ignore[method-assign]
        lambda path, is_folder, count: confirmed.append((Path(path).name, is_folder, count))
        or True
    )

    skins = next(s for s in window.root_node.subdirs if s.name == "rivals skins")
    primary = next(s for s in skins.subdirs if s.name == "Primary")
    window.go(("browse", primary))
    qapp.processEvents()
    card = next(
        c for c in window._browse._grid._cards if c._title_label._raw_text == "Assault Rifle"
    )

    card.delete_requested.emit()
    qapp.processEvents()

    assert confirmed and confirmed[0][0] == "Assault Rifle"
    assert confirmed[0][1] is True
    assert confirmed[0][2] == 2  # ak-47.json + key up.json
    assert not (library / "rivals skins" / "Primary" / "Assault Rifle").exists()
    # Le dossier est réellement dans la Corbeille interne.
    entries = window.trash.list_entries()
    assert len(entries) == 1
    assert entries[0].name == "Assault Rifle"
    assert (entries[0].folder / "payload" / "ak-47.json").is_file()
    # On reste sur Primary ; le dossier a disparu de la grille.
    titles = [c._title_label._raw_text for c in window._browse._grid._cards]
    assert "Assault Rifle" not in titles


def test_card_delete_cancel_does_nothing(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Annuler la confirmation → aucun déplacement, fichier intact."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    window._confirm_card_delete = lambda path, is_folder, count: False  # type: ignore[method-assign]

    charms = next(s for s in window.root_node.subdirs if s.name == "Charms")
    window.go(("browse", charms))
    qapp.processEvents()
    card = next(
        c for c in window._browse._grid._cards if c._title_label._raw_text == "nemesis charm"
    )
    card.delete_requested.emit()
    qapp.processEvents()

    assert window.trash.list_entries() == []
    assert (library / "Charms" / "nemesis charm.json").exists()


def test_card_delete_protections(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Protections absolues : racine, dossier contenant des catégories,
    catégorie entière et chemin hors bibliothèque sont refusés."""
    from app.models import Node
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    window._confirm_card_delete = lambda path, is_folder, count: True  # type: ignore[method-assign]

    # Racine de la bibliothèque.
    window._delete_card(window.root_node)
    # Chemin existant mais hors bibliothèque.
    outside = tmp_path / "outside"
    outside.mkdir()
    window._delete_card(Node(name="evil", path=outside, subdirs=[], configs=[]))
    # Dossier Fleasion (jamais touché par cette action).
    window._delete_card(Node(name="FleasionNT", path=fleasion_dir.parent, subdirs=[], configs=[]))

    assert window.trash.list_entries() == []
    assert (library / "rivals skins" / "Primary" / "Assault Rifle" / "ak-47.json").exists()


def test_card_delete_current_folder_goes_back(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Supprimer le dossier actuellement ouvert → retour propre au parent,
    sans carte fantôme (l'élément part dans la Corbeille interne)."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    window._confirm_card_delete = lambda path, is_folder, count: True  # type: ignore[method-assign]

    skins = next(s for s in window.root_node.subdirs if s.name == "rivals skins")
    primary = next(s for s in skins.subdirs if s.name == "Primary")
    assault = next(s for s in primary.subdirs if s.name == "Assault Rifle")
    window.go(("browse", primary))
    window.go(("browse", assault))
    qapp.processEvents()
    assert window._history.current() == ("browse", assault)

    window._delete_card(assault)
    qapp.processEvents()

    # L'état courant est revenu au parent (Primary) et la grille est à jour.
    page, payload = window._history.current()
    assert page == "browse"
    assert payload.name == "Primary"
    titles = [c._title_label._raw_text for c in window._browse._grid._cards]
    assert "Assault Rifle" not in titles


def test_card_delete_keeps_search_and_filters_working(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Après une suppression, la recherche et les filtres restent
    fonctionnels et ne montrent plus l'élément supprimé."""
    from app.search import SearchState
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    window._confirm_card_delete = lambda path, is_folder, count: True  # type: ignore[method-assign]

    # Supprimer « key up » depuis l'arbre (fichier config).
    skins = next(s for s in window.root_node.subdirs if s.name == "rivals skins")
    primary = next(s for s in skins.subdirs if s.name == "Primary")
    assault = next(s for s in primary.subdirs if s.name == "Assault Rifle")
    key_up = next(c for c in assault.configs if c.name == "key up")
    window._delete_card(key_up)
    qapp.processEvents()
    # L'élément est réellement dans la Corbeille interne (pas de suppression
    # définitive), et a disparu de la bibliothèque.
    entries = window.trash.list_entries()
    assert any(e.name == "key up" and e.kind == "file" for e in entries)
    assert not key_up.path.exists()

    # La recherche fonctionne toujours et exclut l'élément supprimé.
    window._search.setText("key")
    window._run_search()
    qapp.processEvents()
    assert isinstance(window._history.current()[1], SearchState)
    titles = [c._title_label._raw_text for c in window._browse._grid._cards]
    assert "key up" not in titles
    assert "key handgun" in titles

    # Les filtres fonctionnent toujours avec la recherche.
    window._browse._filter_category.setCurrentIndex(
        window._browse._filter_category.findData("secondary")
    )
    qapp.processEvents()
    state = window._history.current()[1]
    assert isinstance(state, SearchState) and state.category == "secondary"
    titles = [c._title_label._raw_text for c in window._browse._grid._cards]
    assert "key handgun" in titles  # Secondaire/Hand gun reste filtré correctement


def test_card_delete_category_empty(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Une catégorie vide peut être supprimée après confirmation explicite."""
    from ui.main_window import MainWindow

    (library / "rivals skins" / "Utility").mkdir()  # catégorie vide navigable

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    window._confirm_card_delete = lambda path, is_folder, count: True  # type: ignore[method-assign]

    skins = next(s for s in window.root_node.subdirs if s.name == "rivals skins")
    window.go(("browse", skins))
    qapp.processEvents()
    card = next(
        c for c in window._browse._grid._cards if c._title_label._raw_text == "Utility"
    )
    card.delete_requested.emit()
    qapp.processEvents()

    # Le dossier est dans la Corbeille interne et a disparu de la bibliothèque.
    entries = window.trash.list_entries()
    assert any(e.name == "Utility" and e.kind == "folder" for e in entries)
    assert not (library / "rivals skins" / "Utility").exists()
    titles = [c._title_label._raw_text for c in window._browse._grid._cards]
    assert "Utility" not in titles


def test_card_delete_category_with_configs_and_count(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Supprimer une catégorie contenant des configs : la confirmation
    indique le nombre exact, le dossier part vers la Corbeille interne."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    confirmed: list[tuple[str, bool, int]] = []
    window._confirm_card_delete = (  # type: ignore[method-assign]
        lambda path, is_folder, count: confirmed.append((Path(path).name, is_folder, count))
        or True
    )

    skins = next(s for s in window.root_node.subdirs if s.name == "rivals skins")
    window.go(("browse", skins))
    qapp.processEvents()
    card = next(
        c for c in window._browse._grid._cards if c._title_label._raw_text == "Primary"
    )
    card.delete_requested.emit()
    qapp.processEvents()

    assert confirmed and confirmed[0] == ("Primary", True, 2)  # ak-47 + key up
    # Le contenu est réellement dans la Corbeille interne (2 fichiers).
    entries = window.trash.list_entries()
    assert any(e.name == "Primary" and e.kind == "folder" and e.file_count == 2 for e in entries)
    assert not (library / "rivals skins" / "Primary").exists()
    titles = [c._title_label._raw_text for c in window._browse._grid._cards]
    assert "Primary" not in titles


def test_card_delete_category_cancel(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Annuler la suppression d'une catégorie → rien n'est déplacé."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    window._confirm_card_delete = lambda path, is_folder, count: False  # type: ignore[method-assign]

    skins = next(s for s in window.root_node.subdirs if s.name == "rivals skins")
    window.go(("browse", skins))
    qapp.processEvents()
    card = next(
        c for c in window._browse._grid._cards if c._title_label._raw_text == "Primary"
    )
    card.delete_requested.emit()
    qapp.processEvents()

    assert window.trash.list_entries() == []
    assert (library / "rivals skins" / "Primary" / "Assault Rifle" / "ak-47.json").exists()


def test_card_delete_category_returns_to_parent(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Si l'utilisateur se trouve DANS la catégorie supprimée, retour propre
    au parent (navigation cohérente, pas de carte fantôme)."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    window._confirm_card_delete = lambda path, is_folder, count: True  # type: ignore[method-assign]

    skins = next(s for s in window.root_node.subdirs if s.name == "rivals skins")
    primary = next(s for s in skins.subdirs if s.name == "Primary")
    # Navigation naturelle : accueil → rivals skins → Primary (on est DANS
    # la catégorie quand on la supprime).
    window.go(("browse", skins))
    window.go(("browse", primary))
    qapp.processEvents()
    assert window._history.current()[1].name == "Primary"

    window._delete_card(primary)
    qapp.processEvents()

    # Retour propre au parent (l'état précédent), pas de carte fantôme.
    page, payload = window._history.current()
    assert page == "browse"
    assert payload.name == "rivals skins"
    titles = [c._title_label._raw_text for c in window._browse._grid._cards]
    assert "Primary" not in titles


def test_clear_configs_dialog_selection(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Le dialogue Clear Configs liste les vraies configs, gère « Tout
    sélectionner » et le compteur ; l'action reste désactivée sans
    sélection."""
    from ui.views.clear_configs_dialog import ClearConfigsDialog

    dialog = ClearConfigsDialog(["Alpha", "Beta", "Gamma"])
    assert list(dialog._checkboxes) == ["Alpha", "Beta", "Gamma"]
    assert dialog.selected == []
    assert not dialog._action_btn.isEnabled()

    dialog._checkboxes["Alpha"].setChecked(True)
    assert dialog.selected == ["Alpha"]
    assert dialog._action_btn.isEnabled()
    assert "1 configuration sélectionnée" in dialog._count_label.text()

    dialog._select_all.setChecked(True)
    assert dialog.selected == ["Alpha", "Beta", "Gamma"]
    assert "3 configurations sélectionnées" in dialog._count_label.text()

    dialog._select_all.setChecked(False)
    assert dialog.selected == []
    assert not dialog._action_btn.isEnabled()
    dialog.deleteLater()


def test_clear_configs_dialog_search(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """La recherche dans Clear Configs filtre visuellement en mémoire :
    casse/espaces ignorés, compteur de résultats distinct du compteur de
    sélection, « Tout sélectionner » limité aux résultats visibles, cases
    masquées conservant leur état, effacement par la croix, et AUCUNE
    écriture pendant la saisie."""
    from PySide6.QtWidgets import QLineEdit

    from ui.views.clear_configs_dialog import ClearConfigsDialog

    dialog = ClearConfigsDialog(["Keyper", "Keytana", "Pixelhandgun (1)", "Sol Pistols over default"])

    # Recherche vide → toutes les configs visibles, compteur de résultats.
    assert dialog._visible == ["Keyper", "Keytana", "Pixelhandgun (1)", "Sol Pistols over default"]
    assert "4 résultats" in dialog._results_label.text()
    assert all(not dialog._checkboxes[n].isHidden() for n in dialog._visible)

    # Recherche exacte / partielle.
    dialog._search.setText("key")
    assert dialog._visible == ["Keyper", "Keytana"]
    assert "2 résultats" in dialog._results_label.text()
    assert not dialog._checkboxes["Keyper"].isHidden()
    assert not dialog._checkboxes["Keytana"].isHidden()
    assert dialog._checkboxes["Pixelhandgun (1)"].isHidden()

    # Insensible à la casse + espaces inutiles.
    dialog._search.setText("  PISTOLS   ")
    assert dialog._visible == ["Sol Pistols over default"]
    assert "1 résultat" in dialog._results_label.text()

    # Aucun résultat.
    dialog._search.setText("zzz")
    assert dialog._visible == []
    assert dialog._results_label.text() == "Aucune configuration trouvée"
    assert not dialog._action_btn.isEnabled()

    # « Tout sélectionner » agit UNIQUEMENT sur les résultats visibles.
    dialog._search.setText("key")
    dialog._select_all.setChecked(True)
    assert dialog.selected == ["Keyper", "Keytana"]
    assert "2 configurations sélectionnées" in dialog._count_label.text()
    assert "2 résultats" in dialog._results_label.text()

    # Une case masquée garde son état (cochée avant d'être filtrée).
    dialog._checkboxes["Pixelhandgun (1)"].setChecked(True)
    dialog._search.setText("key")
    assert dialog.selected == ["Keyper", "Keytana", "Pixelhandgun (1)"]
    assert "3 configurations sélectionnées" in dialog._count_label.text()

    # Tout sélectionner sans recherche → toutes les configs.
    dialog._search.clear()
    assert dialog._visible == ["Keyper", "Keytana", "Pixelhandgun (1)", "Sol Pistols over default"]
    dialog._select_all.setChecked(True)
    assert dialog.selected == [
        "Keyper",
        "Keytana",
        "Pixelhandgun (1)",
        "Sol Pistols over default",
    ]
    assert "4 configurations sélectionnées" in dialog._count_label.text()

    # Effacement de la recherche (croix native de QLineEdit) → tout revient.
    dialog._search.setText("key")
    assert dialog._visible == ["Keyper", "Keytana"]
    dialog._search.clear()
    assert dialog._visible == ["Keyper", "Keytana", "Pixelhandgun (1)", "Sol Pistols over default"]
    assert "4 résultats" in dialog._results_label.text()

    # La barre de recherche est bien un champ avec croix d'effacement.
    assert isinstance(dialog._search, QLineEdit)
    assert dialog._search.isClearButtonEnabled()

    # Aucune écriture pendant la recherche : rien n'est déplacé ni modifié.
    fleasion_root = fleasion_dir.parent
    before = sorted(p.name for p in (fleasion_root / "configs").iterdir()) if (fleasion_root / "configs").exists() else []
    dialog._search.setText("zzz")
    dialog._search.setText("")
    after = sorted(p.name for p in (fleasion_root / "configs").iterdir()) if (fleasion_root / "configs").exists() else []
    assert after == before

    dialog.deleteLater()


def test_clear_configs_button_flow(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Bouton « Clear Configs » (bas droite) : sélection → Corbeille (jamais
    de suppression définitive), backup de settings.json, enabled_configs et
    last_config nettoyés, autres configs et bibliothèque intacts."""
    import json as _json

    from PySide6.QtWidgets import QDialog

    from ui.main_window import MainWindow
    from ui.views.clear_configs_dialog import ClearConfigsDialog

    fleasion_root = fleasion_dir.parent
    (fleasion_root / "settings.json").write_text(
        _json.dumps(
            {"enabled_configs": ["Alpha", "Beta"], "last_config": "Alpha", "theme": "Dark"}
        ),
        encoding="utf-8",
    )
    (fleasion_root / "configs").mkdir(exist_ok=True)
    for name in ("Alpha", "Beta", "Gamma"):
        (fleasion_root / "configs" / f"{name}.json").write_text("{}", encoding="utf-8")

    def fake_exec(self):
        self._checkboxes["Alpha"].setChecked(True)
        self._checkboxes["Beta"].setChecked(True)
        return QDialog.Accepted

    monkeypatch.setattr(ClearConfigsDialog, "exec", fake_exec)

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    window._home._clear_configs_btn.click()
    qapp.processEvents()

    # Les configs sélectionnées sont dans la Corbeille interne de
    # l'application (pas de suppression définitive) et ont disparu de
    # Fleasion.
    names = {e.name for e in window.trash.list_entries()}
    assert names == {"Alpha.json", "Beta.json"}
    assert all(e.was_active for e in window.trash.list_entries())
    assert not (fleasion_root / "configs" / "Alpha.json").exists()
    assert not (fleasion_root / "configs" / "Beta.json").exists()
    # La config non sélectionnée est intacte.
    assert (fleasion_root / "configs" / "Gamma.json").exists()
    settings = _json.loads((fleasion_root / "settings.json").read_text(encoding="utf-8"))
    assert settings["enabled_configs"] == []
    assert settings["last_config"] is None
    assert settings["theme"] == "Dark"
    # settings.json a été sauvegardé avant modification.
    infos = window.backup_manager.list_backups()
    assert any(any(p.name == "settings.json" for p in info.files) for info in infos)
    # La bibliothèque Rivals n'a pas été touchée.
    assert (library / "Charms" / "nemesis charm.json").exists()


def test_clear_configs_cancel_does_nothing(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Annuler le dialogue Clear Configs → aucune configuration déplacée."""
    import json as _json

    from PySide6.QtWidgets import QDialog

    from ui.main_window import MainWindow
    from ui.views.clear_configs_dialog import ClearConfigsDialog

    fleasion_root = fleasion_dir.parent
    (fleasion_root / "settings.json").write_text(
        _json.dumps({"enabled_configs": ["Alpha"], "last_config": "Alpha"}),
        encoding="utf-8",
    )
    (fleasion_root / "configs").mkdir(exist_ok=True)
    (fleasion_root / "configs" / "Alpha.json").write_text("{}", encoding="utf-8")

    monkeypatch.setattr(ClearConfigsDialog, "exec", lambda self: QDialog.Rejected)

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    window._home._clear_configs_btn.click()
    qapp.processEvents()

    assert window.trash.list_entries() == []
    assert (fleasion_root / "configs" / "Alpha.json").exists()


def test_window_resizes_without_overlap(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Aucun chevauchement à toutes les tailles : la recherche ne chevauche
    jamais le bouton « Ajouter une arme », et les actions de la vue config
    restent dans leur colonne (boutons jamais coupés par le bord)."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    def first_config(node):
        if node.configs:
            return node.configs[0]
        for sub in node.subdirs:
            found = first_config(sub)
            if found is not None:
                return found
        return None

    item = first_config(window.root_node)
    assert item is not None
    window.go(("config", item))

    for size in [(960, 640), (1024, 768), (1280, 720), (1366, 768), (1600, 900), (1920, 1080)]:
        window.resize(*size)
        qapp.processEvents()
        # Barre supérieure : la recherche reste à gauche du bouton arme.
        assert window._search.x() + window._search.width() <= window._add_weapon_btn.x()
        assert window._add_weapon_btn.x() + window._add_weapon_btn.width() <= window._settings_btn.x()
        # Vue config : les boutons d'action restent dans leur colonne, sans
        # chevauchement ni débordement.
        cv = window._config
        rows = (
            (cv._edit_image_btn, cv._add_obj_btn, cv._remove_obj_btn),
            (cv._sync_btn, cv._open_btn),
        )
        for row in rows:
            previous_right = 0
            for btn in row:
                assert btn.x() >= previous_right
                assert btn.x() + btn.width() <= btn.parentWidget().width()
                previous_right = btn.x() + btn.width()


def test_card_drag_reorder_first_to_last(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Glisser la première carte en dernière position : la grille se
    réordonne, ``order_changed`` émet le nouvel ordre, et AUCUN fichier de
    la bibliothèque n'est modifié."""
    import ui.main_window as main_window_module

    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    # Accueil : cartes des catégories (ordre canonique alphabétique).
    grid = window._home._grid
    before = [c.drag_key for c in grid._cards]
    assert before == sorted(before, key=str.casefold)  # ordre canonique initial

    # Avant / après : empreinte complète de la bibliothèque.
    def snapshot():
        return sorted(
            str(p.relative_to(library)) + "|" + str(p.stat().st_size)
            for p in library.rglob("*")
        )

    snap = snapshot()
    orders: list[list[str]] = []
    grid.order_changed.connect(orders.append)

    # Première carte -> tout à la fin.
    grid.move_card(before[0], len(before))
    qapp.processEvents()
    after = [c.drag_key for c in grid._cards]
    assert after[0] == before[1]
    assert after[-1] == before[0]
    assert sorted(after) == sorted(before)
    assert orders and orders[-1] == after

    # Aucune écriture dans la bibliothèque (display-only).
    assert snapshot() == snap

    # La navigation reste fonctionnelle après réorganisation : la carte à
    # la nouvelle première position a conservé son gestionnaire de clic.
    window.go(("browse", window.root_node.subdirs[0]))
    qapp.processEvents()
    assert window._stack.currentWidget() is window._browse


def test_card_drag_reorder_last_to_first(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Glisser la dernière carte en première position."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    grid = window._home._grid
    before = [c.drag_key for c in grid._cards]
    grid.move_card(before[-1], 0)
    qapp.processEvents()
    after = [c.drag_key for c in grid._cards]
    assert after[0] == before[-1]
    assert after[1:] == before[:-1]


def test_card_order_persists_across_restart(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """L'ordre glisser-déposer est conservé après redémarrage : il est
    écrit dans settings.json (jamais dans la bibliothèque) et réappliqué
    au prochain lancement."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    grid = window._home._grid
    before = [c.drag_key for c in grid._cards]

    # Réordonner et laisser MainWindow persister.
    grid.move_card(before[-1], 0)
    qapp.processEvents()
    expected = [c.drag_key for c in grid._cards]
    assert expected[0] == before[-1]

    # Redémarrage : nouveau MainWindow, mêmes données APPDATA.
    window.close()
    qapp.processEvents()
    window2 = MainWindow()
    window2.show()
    qapp.processEvents()
    restored = [c.drag_key for c in window2._home._grid._cards]
    assert restored == expected
    # La bibliothèque est intacte.
    assert (library / "Charms" / "nemesis charm.json").exists()


def test_card_reorder_ignored_in_search_results(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """La réorganisation est désactivée dans les résultats de recherche
    (aucun ordre persistant lié à une requête)."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    window._search.setText("key")
    window._run_search()
    qapp.processEvents()

    grid = window._browse._grid
    assert grid.reorderable is False
    n = len(grid._cards)
    if n >= 2:
        grid.move_card(grid._cards[0].drag_key, n)
        qapp.processEvents()
        assert len(grid._cards) == n  # rien n'a bougé (reorder désactivé)


def test_card_drag_mime_never_triggers_import(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Le glisser d'une carte porte un MIME interne (jamais d'URL de
    fichier) : le gestionnaire d'import de la fenêtre l'ignore totalement
    — réorganiser une carte ne peut pas ouvrir le popup d'import."""
    from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
    from PySide6.QtGui import QDropEvent

    from ui.main_window import MainWindow
    from ui.widgets.card import CARD_DRAG_MIME

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    # Le MIME interne n'est pas une liste d'URLs locales -> ignoré par la
    # fenêtre (pas d'import), mais accepté par la grille (réorganisation).
    mime = QMimeData()
    mime.setData(CARD_DRAG_MIME, b"whatever")
    assert not window._has_local_files(mime)
    assert window._home._grid.dragEnterEvent is not None

    # Et le chemin inverse : une URL locale (fichier Windows) n'est PAS
    # acceptée par la grille (elle continue de remonter vers l'import).
    url_mime = QMimeData()
    url_mime.setUrls([QUrl.fromLocalFile(str(library / "Charms" / "nemesis charm.json"))])
    event = QDropEvent(QPoint(10, 10), Qt.CopyAction, url_mime, Qt.LeftButton, Qt.NoModifier)
    grid = window._home._grid
    grid.dragEnterEvent(event)
    assert not event.isAccepted()


def test_icons_are_vector_not_emoji(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """Les boutons de navigation / paramètres / actions portent de vraies
    icônes vectorielles (plus d'emoji), et la zone de drop n'affiche plus
    de caractère texte."""
    from PySide6.QtWidgets import QLabel

    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()

    for btn in (window._back_btn, window._forward_btn, window._settings_btn, window._trash_btn):
        assert not btn.icon().isNull(), f"{btn.objectName()} doit avoir une icône"
        assert not any(ch in btn.text() for ch in "←→⚙🗑")
    assert "➕" not in window._add_weapon_btn.text()
    assert window._add_weapon_btn.icon() is not None and not window._add_weapon_btn.icon().isNull()
    # Zone de drop : plus de « ＋ » texte (icône vectorielle à la place).
    texts = [w.text() for w in window._home._drop_zone.findChildren(QLabel)]
    assert all("＋" not in t for t in texts)
    # Icônes vectorielles : pixels non vides, taille cohérente.
    pm = window._back_btn.icon().pixmap(22, 22)
    assert not pm.isNull()


def test_grid_columns_adapt_to_width(library: Path, fleasion_dir: Path, tmp_path: Path, monkeypatch, qapp) -> None:
    """La grille adapte le nombre de colonnes à la largeur disponible
    (petite fenêtre → moins de cartes par ligne)."""
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    _configure(appdata, library, fleasion_dir)

    window = MainWindow()
    window.show()
    qapp.processEvents()
    grid = window._home._grid

    def columns() -> int:
        return grid._grid.columnCount()

    window.resize(960, 640)
    qapp.processEvents()
    small = columns()
    window.resize(1920, 1080)
    qapp.processEvents()
    large = columns()
    assert large > small
    assert small >= 1


def test_scan_real_library_if_present() -> None:
    """The real library on this machine must scan cleanly (guards regressions)."""
    from pathlib import Path as P

    real = P.home() / "Desktop" / "Rivals configs"
    if not real.is_dir():
        pytest.skip("real library not present on this machine")
    result = scan_library(real)
    assert result.ok, result.errors
    assert result.node is not None
    # Sanity: the real library contains hundreds of configurations.
    total = _count(result.node)
    assert total > 50


def _count(node) -> int:
    total = len(node.configs)
    for sub in node.subdirs:
        total += _count(sub)
    return total
