"""v1.3.8 — onboarding de première utilisation (choix de langue + tutoriel).

Covers:

* premier lancement : aucune langue → écran de choix ; langue appliquée et
  sauvegardée ; tutoriel lancé ensuite dans la langue choisie ;
* lancements suivants : langue déjà enregistrée → pas de re-demande ;
  tutoriel terminé → plus jamais d'onboarding ;
* tutoriel : 8 étapes, cibles valides, traductions, suivant / précédent /
  terminer, indicateur de progression ;
* persistance : terminer → `onboarding_completed = true` ; fermeture en
  cours de tutoriel → jamais marqué comme terminé par erreur ; langue /
  thème / favoris / chemins conservés ; changer de langue après coup ne
  réaffiche pas le tutoriel ;
* responsive : petite / moyenne / grande fenêtre, plein écran → fenêtre et
  fenêtre → plein écran : la bulle et le spotlight restent dans la fenêtre.

The onboarding auto-start is normally disabled in tests (conftest sets
``RCM_ONBOARDING=0``); these tests opt back in with ``=1`` and drive the
language dialog through an injectable factory so nothing blocks.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QApplication, QDialog


# ---------------------------------------------------------------------- #
# Fixtures / helpers
# ---------------------------------------------------------------------- #
@pytest.fixture()
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _library(root: Path) -> Path:
    lib = root / "lib"
    _write_json(lib / "Charms" / "charm 0.json", {"replacement_rules": []})
    _write_json(lib / "rivals skins" / "Primary" / "Assault Rifle" / "skin 0.json",
                {"replacement_rules": []})
    return lib


def _write_app_settings(appdata: Path, library: Path, fleasion: Path,
                        language: str | None = None,
                        completed: bool = False) -> Path:
    data = {"library_dir": str(library), "fleasion_dir": str(fleasion)}
    if language is not None:
        data["language"] = language
    if completed:
        data["onboarding_completed"] = True
    path = appdata / "RivalsConfigManager" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _make_env(tmp_path, monkeypatch, *, language=None, completed=False):
    """Configure a fresh APPDATA + library + Fleasion, enable onboarding."""
    monkeypatch.setenv("RCM_ONBOARDING", "1")
    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    lib = _library(tmp_path)
    fleasion = tmp_path / "fleasion"
    fleasion.mkdir(parents=True)
    (fleasion / "settings.json").write_text("{}", encoding="utf-8")
    settings_path = _write_app_settings(appdata, lib, fleasion, language, completed)
    return appdata, lib, fleasion, settings_path


class _FakeLangDialog:
    """Fake language dialog: always accepts, always returns ``code``."""

    def __init__(self, code: str = "en", parent=None) -> None:
        self.code = code
        self.calls = 0

    def exec(self) -> int:
        self.calls += 1
        return QDialog.DialogCode.Accepted

    @property
    def selected_code(self) -> str:
        return self.code


class _BoomLangDialog:
    """Raises if constructed — proves the language screen was NOT asked."""

    def __init__(self, *args, **kwargs) -> None:
        raise AssertionError("l'écran de choix de langue ne doit pas s'afficher")


def _open(window, qapp) -> None:
    window.show()
    qapp.processEvents()


def _install_language_factory(window, factory) -> None:
    """Replace the dialog factory before the deferred onboarding runs.
    ``factory`` is a callable ``(parent=None) -> dialog`` — pass a class or
    a lambda, never an already-constructed instance."""
    window._language_dialog_factory = factory


# ---------------------------------------------------------------------- #
# 1. Premier lancement — choix de langue puis tutoriel
# ---------------------------------------------------------------------- #
def test_first_launch_language_choice_and_tutorial(qapp, tmp_path, monkeypatch) -> None:
    """Aucune langue enregistrée → écran de langue ; la langue choisie est
    appliquée et sauvegardée ; le tutoriel démarre ensuite (8 étapes)."""
    from ui.main_window import MainWindow

    appdata, lib, fleasion, settings_path = _make_env(tmp_path, monkeypatch)
    fake = _FakeLangDialog("en")
    window = MainWindow()
    _install_language_factory(window, lambda parent=None: fake)
    _open(window, qapp)

    # La langue a été demandée, appliquée et persistée.
    assert fake.calls == 1
    assert window.settings.language == "en"
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    assert payload["language"] == "en"
    # Le tutoriel a démarré dans la langue choisie.
    overlay = window._onboarding_overlay
    assert overlay is not None
    assert overlay.step_count == 9
    assert overlay.bubble._title.text()  # non vide
    window.close()


def test_first_launch_cancel_keeps_default_and_tutorial(qapp, tmp_path, monkeypatch) -> None:
    """Fermer l'écran de langue sans choisir : pas de crash, langue par
    défaut (English depuis 1.3.13) conservée, tutoriel tout de même
    proposé (il n'est pas fini)."""
    from ui.main_window import MainWindow

    appdata, lib, fleasion, settings_path = _make_env(tmp_path, monkeypatch)

    class _Cancel:
        def exec(self) -> int:
            return QDialog.DialogCode.Rejected

        @property
        def selected_code(self) -> str:
            return "en"

    window = MainWindow()
    _install_language_factory(window, lambda parent=None: _Cancel())
    _open(window, qapp)
    assert window.settings.language == "en"  # défaut intact (1.3.13)
    assert window._onboarding_overlay is not None  # tutoriel proposé
    window.close()


def test_language_already_saved_no_reask_tutorial_direct(qapp, tmp_path, monkeypatch) -> None:
    """Langue déjà enregistrée mais tutoriel non terminé → pas de re-demande
    de langue, tutoriel affiché directement dans la langue enregistrée."""
    from ui.main_window import MainWindow

    appdata, lib, fleasion, settings_path = _make_env(tmp_path, monkeypatch, language="de")
    window = MainWindow()
    _install_language_factory(window, _BoomLangDialog)
    _open(window, qapp)

    assert window.settings.language == "de"
    assert window._onboarding_overlay is not None
    # Le tutoriel est dans la langue enregistrée (allemand).
    assert window._onboarding_overlay.bubble._title.text() == "Dateien hinzufügen"
    window.close()


def test_onboarding_completed_nothing_shown(qapp, tmp_path, monkeypatch) -> None:
    """Langue enregistrée ET tutoriel terminé → ni écran de langue, ni
    tutoriel : l'application démarre normalement."""
    from ui.main_window import MainWindow

    appdata, lib, fleasion, settings_path = _make_env(tmp_path, monkeypatch,
                                                      language="fr", completed=True)
    window = MainWindow()
    _install_language_factory(window, _BoomLangDialog)
    _open(window, qapp)

    assert window._onboarding_overlay is None
    assert window._tutorial_pending is False
    assert window.settings.onboarding_completed is True
    window.close()


# ---------------------------------------------------------------------- #
# 1b. Reset développement — installation vierge sans rien supprimer
# ---------------------------------------------------------------------- #
def test_reset_onboarding_env_var_preserves_everything(qapp, tmp_path, monkeypatch) -> None:
    """``RCM_RESET_ONBOARDING=1`` remet à zéro UNIQUEMENT la langue choisie
    et le tutoriel — favoris, thème, chemins et autres préférences restent
    intacts ; jamais actif par défaut."""
    from app.config import AppSettings, settings_file

    appdata, lib, fleasion, settings_path = _make_env(tmp_path, monkeypatch,
                                                      language="de", completed=True)
    skin = lib / "rivals skins" / "Primary" / "Assault Rifle" / "skin 0.json"
    data = json.loads(settings_path.read_text(encoding="utf-8"))
    data["favorites"] = [str(skin)]
    data["theme"] = "midnight"
    settings_path.write_text(json.dumps(data), encoding="utf-8")

    # Sans la variable : rien n'est réinitialisé.
    monkeypatch.delenv("RCM_RESET_ONBOARDING", raising=False)
    s = AppSettings.load()
    assert s.language_chosen is True and s.onboarding_completed is True

    # Avec la variable : reset onboarding uniquement.
    monkeypatch.setenv("RCM_RESET_ONBOARDING", "1")
    s2 = AppSettings.load()
    assert s2.language_chosen is False
    assert s2.onboarding_completed is False
    # Tout le reste est conservé.
    assert s2.favorites == [str(skin)]
    assert s2.theme == "midnight"
    assert s2.library_dir == lib
    assert s2.fleasion_dir == fleasion
    assert s2.language == "de"  # la langue choisie reste la langue par défaut de l'app
    # L'état reset est persisté.
    payload = json.loads(settings_file().read_text(encoding="utf-8"))
    assert payload.get("onboarding_completed") is False

    # Sans la variable, l'état reste reset (persisté).
    monkeypatch.delenv("RCM_RESET_ONBOARDING", raising=False)
    s3 = AppSettings.load()
    assert s3.language_chosen is False and s3.onboarding_completed is False
    assert s3.favorites == [str(skin)] and s3.theme == "midnight"


def test_reset_onboarding_function(qapp, tmp_path, monkeypatch) -> None:
    """La fonction dédiée ``reset_onboarding`` fait le même reset propre."""
    from app.onboarding import reset_onboarding

    appdata, lib, fleasion, settings_path = _make_env(tmp_path, monkeypatch,
                                                      language="fr", completed=True)
    skin = lib / "rivals skins" / "Primary" / "Assault Rifle" / "skin 0.json"
    from app.config import AppSettings

    settings = AppSettings.load()
    settings.favorites = [str(skin)]
    reset_onboarding(settings)
    assert settings.language_chosen is False
    assert settings.onboarding_completed is False
    assert settings.favorites == [str(skin)]

    reloaded = AppSettings.load()
    assert reloaded.onboarding_completed is False
    assert reloaded.favorites == [str(skin)]


def test_virgin_install_after_reset_shows_language_then_tutorial(qapp, tmp_path,
                                                                 monkeypatch) -> None:
    """Après le reset, un lancement se comporte comme une installation
    vierge : écran de langue → langue appliquée → tutoriel dans cette
    langue — les chemins configurés restent utilisés."""
    from ui.main_window import MainWindow

    appdata, lib, fleasion, settings_path = _make_env(tmp_path, monkeypatch,
                                                      language="fr", completed=True)
    monkeypatch.setenv("RCM_RESET_ONBOARDING", "1")
    fake = _FakeLangDialog("en")
    window = MainWindow()
    _install_language_factory(window, lambda parent=None: fake)
    _open(window, qapp)

    assert fake.calls == 1          # écran de langue demandé
    assert window.settings.language == "en"  # appliquée
    assert window._onboarding_overlay is not None  # tutoriel lancé ensuite
    # La langue choisie est dans le tutoriel.
    assert window._onboarding_overlay.bubble._title.text()
    # Les chemins configurés sont conservés et utilisés.
    assert window.settings.library_dir == lib
    assert window.settings.fleasion_dir == fleasion
    window.close()


# ---------------------------------------------------------------------- #
# 2. Écran de choix de langue — les 10 langues
# ---------------------------------------------------------------------- #
def test_language_dialog_lists_10_languages(qapp) -> None:
    """Le modal propose les 10 langues supportées (noms natifs) et renvoie
    le code choisi."""
    from app.i18n import available_languages
    from ui.views.language_dialog import LanguageDialog

    dlg = LanguageDialog()
    assert dlg._list.count() == 10
    assert dlg._list.count() == len(available_languages())
    # La langue courante est présélectionnée.
    from app.i18n import current_language

    current = current_language()
    assert dlg._list.currentItem().data(int(Qt.UserRole)) == current
    # Choisir « English » → selected_code == "en".
    for i in range(dlg._list.count()):
        if dlg._list.item(i).data(int(Qt.UserRole)) == "en":
            dlg._list.setCurrentRow(i)
            break
    assert dlg.selected_code == "en"
    dlg.deleteLater()


# ---------------------------------------------------------------------- #
# 3. Tutoriel — étapes, navigation, progression, terminaison
# ---------------------------------------------------------------------- #
def _tutorial_window(qapp, tmp_path, monkeypatch):
    from ui.main_window import MainWindow

    appdata, lib, fleasion, settings_path = _make_env(tmp_path, monkeypatch, language="fr")
    window = MainWindow()
    _install_language_factory(window, _BoomLangDialog)
    _open(window, qapp)
    assert window._onboarding_overlay is not None
    return window, window._onboarding_overlay, settings_path


def test_tutorial_9_steps_valid_targets_and_translations(qapp, tmp_path, monkeypatch) -> None:
    """Les 9 étapes existent, chacune a une cible réelle dans la fenêtre et
    des traductions (jamais la clé brute affichée)."""
    from app.i18n import t

    window, overlay, _ = _tutorial_window(qapp, tmp_path, monkeypatch)
    assert overlay.step_count == 9
    for i in range(overlay.step_count):
        rect = overlay.target_rect(i)
        assert not rect.isNull() and not rect.isEmpty(), f"étape {i} : cible invalide"
        assert rect.left() >= 0 and rect.top() >= 0, f"étape {i} : cible hors fenêtre"
        step = overlay._steps[i]
        assert t(step["title"]) != step["title"], f"étape {i} : titre non traduit"
        assert t(step["body"]) != step["body"], f"étape {i} : texte non traduit"
    window.close()


def test_tutorial_next_prev_progress_and_finish(qapp, tmp_path, monkeypatch) -> None:
    """Suivant / Précédent / Terminer fonctionnent ; l'indicateur de
    progression est correct ; « Compris » persiste la fin du tutoriel."""
    window, overlay, settings_path = _tutorial_window(qapp, tmp_path, monkeypatch)

    n = overlay.step_count
    # Étape 1 : « Précédent » désactivé, progression 1 / n.
    assert overlay.bubble._progress.text() == f"1 / {n}"
    assert not overlay.bubble._prev_btn.isEnabled()

    # Avancer jusqu'à la dernière étape.
    for expected in range(2, n + 1):
        overlay.bubble._next_btn.click()
        assert overlay.current_step == expected - 1
        assert overlay.bubble._progress.text() == f"{expected} / {n}"
    # Dernière étape : le bouton devient « Terminer ».
    assert overlay.bubble._next_btn.text() == "Terminer"

    # Précédent ramène bien en arrière.
    overlay.bubble._prev_btn.click()
    assert overlay.bubble._progress.text() == f"{n - 1} / {n}"
    overlay.bubble._next_btn.click()
    assert overlay.bubble._progress.text() == f"{n} / {n}"

    # Terminer → écran « Vous êtes prêt ! » puis « Compris ».
    overlay.bubble._next_btn.click()  # étape 8 → écran final
    assert overlay.current_step == overlay.step_count
    assert overlay.bubble._got_it_btn.isVisible()
    assert "prêt" in overlay.bubble._title.text().lower()

    window.settings.theme = "midnight"  # une préférence arbitraire conservée
    overlay.bubble._got_it_btn.click()
    assert window.settings.onboarding_completed is True
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    assert payload["onboarding_completed"] is True
    assert window._onboarding_overlay is None  # fermé proprement
    window.close()


def test_after_completion_restart_shows_nothing(qapp, tmp_path, monkeypatch) -> None:
    """Après « Compris », un redémarrage ne montre plus jamais l'onboarding
    — et langue / thème / favoris / chemins sont conservés."""
    from app.config import settings_file
    from ui.main_window import MainWindow

    window, overlay, settings_path = _tutorial_window(qapp, tmp_path, monkeypatch)
    lib = window.settings.library_dir
    skin = lib / "rivals skins" / "Primary" / "Assault Rifle" / "skin 0.json"
    window.settings.toggle_favorite(str(skin))
    window.settings.theme = "midnight"
    for _ in range(overlay.step_count + 1):
        overlay.bubble._next_btn.click()
    overlay.bubble._got_it_btn.click()
    window.close()

    window2 = MainWindow()
    _install_language_factory(window2, _BoomLangDialog)
    _open(window2, qapp)
    assert window2._onboarding_overlay is None
    assert window2.settings.onboarding_completed is True
    assert window2.settings.theme == "midnight"
    assert str(skin) in window2.settings.favorites
    assert window2.settings.library_dir == lib
    assert window2.settings.fleasion_dir == window.settings.fleasion_dir
    window2.close()


def test_close_during_tutorial_never_marks_completed(qapp, tmp_path, monkeypatch) -> None:
    """Fermer l'application pendant le tutoriel : rien n'est corrompu, le
    tutoriel n'est PAS considéré comme terminé — il revient au prochain
    lancement (avec la langue déjà choisie, sans re-demander)."""
    from app.config import settings_file
    from ui.main_window import MainWindow

    window, overlay, settings_path = _tutorial_window(qapp, tmp_path, monkeypatch)
    overlay.next()  # on a avancé de quelques étapes…
    overlay.next()
    window.close()

    payload = json.loads(settings_file().read_text(encoding="utf-8"))
    assert payload.get("onboarding_completed") is not True
    assert payload["language"] == "fr"

    window2 = MainWindow()
    _install_language_factory(window2, _BoomLangDialog)
    _open(window2, qapp)
    assert window2._onboarding_overlay is not None  # tutoriel à nouveau
    assert window2.settings.language == "fr"        # langue conservée
    window2.close()


def test_language_change_after_completion_does_not_restart_tutorial(qapp, tmp_path,
                                                                    monkeypatch) -> None:
    """Changer la langue dans les Paramètres après avoir terminé : le
    tutoriel ne réapparaît jamais (choix de langue ≠ état du tutoriel)."""
    from ui.main_window import MainWindow

    window, overlay, settings_path = _tutorial_window(qapp, tmp_path, monkeypatch)
    for _ in range(overlay.step_count + 1):
        overlay.bubble._next_btn.click()
    overlay.bubble._got_it_btn.click()
    window._set_language("en")  # comme depuis les Paramètres
    assert window.settings.onboarding_completed is True
    window.close()

    window2 = MainWindow()
    _install_language_factory(window2, _BoomLangDialog)
    _open(window2, qapp)
    assert window2._onboarding_overlay is None
    assert window2.settings.language == "en"
    window2.close()


# ---------------------------------------------------------------------- #
# 4. Responsive — bulle et spotlight jamais hors fenêtre
# ---------------------------------------------------------------------- #
def test_tutorial_responsive_all_sizes_and_fullscreen(qapp, tmp_path, monkeypatch) -> None:
    """À 960 / 1024 / 1280 / 1366 / 1600 / 1920, en fenêtre → plein écran →
    fenêtre, la bulle et le spotlight restent dans la fenêtre à chaque
    étape du tutoriel."""
    window, overlay, _ = _tutorial_window(qapp, tmp_path, monkeypatch)

    def bubble_inside() -> bool:
        o = overlay.rect()
        b = overlay.bubble.geometry()
        return (b.left() >= 0 and b.top() >= 0
                and b.right() <= o.width() and b.bottom() <= o.height())

    sizes = [(960, 640), (1024, 768), (1280, 720), (1366, 768), (1600, 900), (1920, 1080)]
    for step in range(overlay.step_count + 1):
        overlay._index = step
        overlay._refresh()
        for size in sizes:
            window.resize(*size)
            qapp.processEvents()
            assert bubble_inside(), f"étape {step} taille {size} : bulle hors fenêtre"
            if step < overlay.step_count:
                r = overlay.target_rect(step)
                assert r.right() <= overlay.width() and r.bottom() <= overlay.height()

    # Fenêtre → plein écran → fenêtre.
    overlay._index = 0
    window.showFullScreen()
    qapp.processEvents()
    assert bubble_inside()
    window.showNormal()
    qapp.processEvents()
    assert bubble_inside()
    window.close()


# ---------------------------------------------------------------------- #
# 5. v1.3.9 — présentation du choix de langue + géométrie spotlight/bulle
# ---------------------------------------------------------------------- #
def test_language_dialog_modern_presentation(qapp) -> None:
    """L'écran de langue est clair et esthétique : titre explicite,
    sous-titre, les 10 langues en noms natifs, gros bouton principal."""
    from app.i18n import language_display_name
    from ui.views.language_dialog import LanguageDialog

    dlg = LanguageDialog()
    assert dlg._title.text() == "Choisissez votre langue"
    assert dlg._body.text()
    assert dlg._list.count() == 10
    # Les noms natifs sont affichés.
    for i in range(dlg._list.count()):
        code = dlg._list.item(i).data(int(Qt.UserRole))
        assert dlg._list.item(i).text() == language_display_name(code)
    assert "Français" in [dlg._list.item(i).text() for i in range(10)]
    assert "Русский" in [dlg._list.item(i).text() for i in range(10)]
    # Bouton principal bien visible.
    assert dlg._continue_btn.text() == "Continuer"
    assert dlg.width() >= 460 and dlg.height() >= 540
    dlg.deleteLater()


def test_tutorial_spotlight_and_bubble_geometry_all_steps(qapp, tmp_path, monkeypatch) -> None:
    """Pour chaque étape et chaque taille (dont petite fenêtre et plein
    écran → fenêtre) : spotlight exactement sur la cible et dans la
    fenêtre, bulle dans la fenêtre, bulle qui ne masque pas la cible,
    flèche cohérente avec le placement."""
    window, overlay, _ = _tutorial_window(qapp, tmp_path, monkeypatch)

    sizes = [(560, 420), (960, 640), (1024, 768), (1280, 720),
             (1366, 768), (1600, 900), (1920, 1080)]

    def check(step: int) -> None:
        done = step >= overlay.step_count
        target = overlay.spotlight_rect
        o = overlay.rect()
        if not done:
            # Spotlight = cible réelle, dans la fenêtre.
            assert target == overlay.target_rect(step), f"étape {step}"
            assert target.left() >= 0 and target.top() >= 0
            assert target.right() <= o.width() and target.bottom() <= o.height()
        bubble = overlay.bubble.geometry()
        # Bulle entièrement dans la fenêtre.
        assert bubble.left() >= 0 and bubble.top() >= 0
        assert bubble.right() <= o.width() and bubble.bottom() <= o.height(), \
            f"étape {step} taille {o.width()}x{o.height()}"
        if not done:
            # La bulle ne masque pas la cible.
            assert not bubble.intersects(target), f"étape {step} : bulle sur la cible"
            # La flèche est cohérente avec le placement choisi.
            side = overlay.bubble._arrow_side
            if bubble.top() > target.bottom():
                assert side == 0, f"étape {step} : bulle en dessous → flèche vers le haut"
            elif bubble.bottom() < target.top():
                assert side == 1, f"étape {step} : bulle au-dessus → flèche vers le bas"
            elif bubble.left() > target.right():
                assert side == 2, f"étape {step} : bulle à droite → flèche vers la gauche"
            elif bubble.right() < target.left():
                assert side == 3, f"étape {step} : bulle à gauche → flèche vers la droite"

    for step in range(overlay.step_count + 1):
        overlay._index = step
        overlay._refresh()
        for size in sizes:
            window.resize(*size)
            qapp.processEvents()
            qapp.processEvents()  # le repositionnement différé lit la géométrie finale
            check(step)

    # Plein écran → fenêtre et plusieurs redimensionnements consécutifs :
    # tout est recalculé, jamais besoin de fermer/rouvrir le tutoriel.
    overlay._index = 0
    overlay._refresh()
    window.showFullScreen()
    qapp.processEvents()
    qapp.processEvents()
    check(0)
    window.showNormal()
    qapp.processEvents()
    qapp.processEvents()
    # Séquence exacte de la spec : fenêtre normale → grande fenêtre → plein
    # écran → fenêtre normale → petite fenêtre → grande fenêtre.
    for size in [(1600, 900), (1920, 1080), (960, 640), (1600, 900)]:
        window.resize(*size)
        qapp.processEvents()
        qapp.processEvents()
        check(0)
    # Maximiser / restaurer (fenêtre normale comme cas principal).
    window.showMaximized()
    qapp.processEvents()
    qapp.processEvents()
    check(0)
    window.showNormal()
    qapp.processEvents()
    qapp.processEvents()
    check(0)
    window.close()


def test_stale_spotlight_self_heals(qapp, tmp_path, monkeypatch) -> None:
    """Le bug signalé : un spotlight qui garde la géométrie d'une ANCIENNE
    taille de fenêtre (« énorme rectangle »). La boucle de stabilisation /
    le filet de sécurité doivent le recaler sur la vraie cible sans qu'il
    soit besoin de fermer/réouvrir le tutoriel."""
    from PySide6.QtCore import QRect

    window, overlay, _ = _tutorial_window(qapp, tmp_path, monkeypatch)
    window.resize(1280, 800)
    qapp.processEvents()

    real = overlay.target_rect(0)
    # Injecte une géométrie périmée (ancienne taille maximisée).
    overlay._target = QRect(10, 60, 1800, 400)
    overlay.update()
    assert overlay.spotlight_rect != real

    # Laisse la boucle de stabilisation / le filet de sécurité converger.
    qapp.processEvents()
    for _ in range(6):
        overlay._settle_tick()
        overlay._poll_tick()
        qapp.processEvents()
    assert overlay.spotlight_rect == real
    window.close()


def test_review_tutorial_from_settings(qapp, tmp_path, monkeypatch) -> None:
    """« Revoir le tutoriel » dans les Paramètres : tutoriel relancé
    immédiatement, sans écran de langue, langue et préférences intactes,
    navigation ramenée à l'accueil, terminer remet completed=true."""
    from ui.main_window import MainWindow

    appdata, lib, fleasion, settings_path = _make_env(tmp_path, monkeypatch,
                                                      language="fr", completed=True)
    window = MainWindow()
    _install_language_factory(window, _BoomLangDialog)
    _open(window, qapp)
    assert window._onboarding_overlay is None  # terminé → rien au démarrage

    window.go(("settings", None))
    qapp.processEvents()
    btn = window._settings._review_tutorial_btn
    assert btn.isVisible()
    assert "tutoriel" in btn.text().lower()

    btn.click()
    qapp.processEvents()
    assert window._onboarding_overlay is not None  # tutoriel relancé
    assert window._stack.currentWidget() is window._home  # retour accueil
    assert window.settings.language == "fr"  # langue conservée
    assert window.settings.library_dir == lib  # chemins conservés

    overlay = window._onboarding_overlay
    for _ in range(overlay.step_count + 1):
        overlay.bubble._next_btn.click()
    overlay.bubble._got_it_btn.click()
    assert window.settings.onboarding_completed is True
    assert window._onboarding_overlay is None
    window.close()


def test_restart_during_tutorial(qapp, tmp_path, monkeypatch) -> None:
    """Recharger l'application pendant le tutoriel : pas de crash, l'état
    n'est pas corrompu, le tutoriel n'est pas marqué terminé par erreur."""
    import ui.main_window as mw
    from app.config import settings_file
    from ui.main_window import MainWindow

    window, overlay, settings_path = _tutorial_window(qapp, tmp_path, monkeypatch)
    spawned = {}
    monkeypatch.setattr(mw, "relaunch",
                        lambda *a, **k: (spawned.update(called=True), object())[1])
    window._restart_app()
    qapp.processEvents()

    assert spawned.get("called") is True
    assert not window.isVisible()
    payload = json.loads(settings_file().read_text(encoding="utf-8"))
    assert payload.get("onboarding_completed") is not True
    assert payload["language"] == "fr"

    # Au lancement suivant : tutoriel à nouveau (non terminé).
    window2 = MainWindow()
    _install_language_factory(window2, _BoomLangDialog)
    _open(window2, qapp)
    assert window2._onboarding_overlay is not None
    window2.close()


def test_tutorial_does_not_interact_with_app_underneath(qapp, tmp_path, monkeypatch) -> None:
    """Pendant une étape, cliquer sur l'application (hors bulle) est avalé
    par l'overlay : la navigation ne change pas sans passer par le tutoriel."""
    from PySide6.QtCore import QEvent, QPointF, Qt
    from PySide6.QtGui import QMouseEvent

    window, overlay, _ = _tutorial_window(qapp, tmp_path, monkeypatch)
    page_before = window._stack.currentWidget()
    pos = QPointF(5, 5)  # coin de la fenêtre, sous l'overlay
    press = QMouseEvent(QEvent.MouseButtonPress, pos, pos, Qt.LeftButton,
                        Qt.LeftButton, Qt.NoModifier)
    overlay.mousePressEvent(press)
    release = QMouseEvent(QEvent.MouseButtonRelease, pos, pos, Qt.LeftButton,
                          Qt.NoButton, Qt.NoModifier)
    overlay.mouseReleaseEvent(release)
    qapp.processEvents()
    assert window._stack.currentWidget() is page_before
    window.close()


# ---------------------------------------------------------------------- #
# 6. v1.3.10 — rendu du voile (semi-transparent, cible éclairée)
# ---------------------------------------------------------------------- #
def test_veil_is_semi_transparent_not_opaque() -> None:
    """Le voile n'est PAS noir opaque : son opacité est dans la fourchette
    50–65 % demandée — l'application reste visible derrière le tutoriel."""
    from ui.widgets.onboarding_overlay import _VEIL_ALPHA, _VEIL_ALPHA_NEAR

    opacity = _VEIL_ALPHA / 255.0
    assert 0.50 <= opacity <= 0.65
    # La zone autour du spotlight est LÉGÈREMENT plus claire que le reste.
    assert 0 < _VEIL_ALPHA_NEAR < _VEIL_ALPHA


def test_veil_rendering_app_visible_and_target_clear(qapp, tmp_path, monkeypatch) -> None:
    """Rendu pixel réel : loin du spotlight l'application est assombrie mais
    jamais noire opaque (on la devine encore derrière), la zone autour de la
    cible est plus claire que les coins, et la cible elle-même est
    parfaitement visible (trou 100 % transparent dans le voile)."""
    from PySide6.QtCore import QPoint, QRect, Qt
    from PySide6.QtGui import QImage, QRegion
    from PySide6.QtWidgets import QWidget

    window, overlay, _ = _tutorial_window(qapp, tmp_path, monkeypatch)
    overlay._index = 0
    overlay._refresh()
    qapp.processEvents()
    overlay.bubble.hide()  # la bulle ne gêne pas le contrôle du voile

    size = overlay.size()
    image = QImage(size, QImage.Format_ARGB32)
    image.fill(Qt.transparent)
    # Uniquement le rendu du voile (sans le fond opaque du widget).
    overlay.render(image, QPoint(), QRegion(), QWidget.RenderFlag.DrawChildren)

    target = overlay.spotlight_rect
    assert not target.isNull()
    c = target.center()
    w, h = size.width(), size.height()
    corners = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
    far = max(corners, key=lambda p: (p[0] - c.x()) ** 2 + (p[1] - c.y()) ** 2)
    far_px = image.pixelColor(far[0], far[1])
    assert far_px.alpha() > 0  # le voile est bien là
    # Composé sur un fond rouge vif (l'application) : assombri, jamais noir.
    red = (far_px.red() * far_px.alpha() + 255 * (255 - far_px.alpha())) // 255
    assert 0 < red < 255, f"voile {far_px.alpha()} : app invisible ou non assombrie"

    # Autour du spotlight : plus clair qu'aux coins (effet « éclairé ») —
    # on prend un point juste à l'extérieur du trou, dans le voile.
    near = None
    if target.right() + 40 < w:
        near = QPoint(target.right() + 40, c.y())
    elif target.left() - 40 >= 0:
        near = QPoint(target.left() - 40, c.y())
    elif target.bottom() + 40 < h:
        near = QPoint(c.x(), target.bottom() + 40)
    elif target.top() - 40 >= 0:
        near = QPoint(c.x(), target.top() - 40)
    if near is not None:
        near_px = image.pixelColor(near.x(), near.y())
        assert 0 < near_px.alpha() < far_px.alpha()

    # La cible : trou totalement transparent → l'élément est parfaitement
    # visible à travers le voile.
    cx = min(max(c.x(), 1), w - 2)
    cy = min(max(c.y(), 1), h - 2)
    hole_px = image.pixelColor(cx, cy)
    assert hole_px.alpha() == 0, "la cible ne doit pas être cachée par le voile"
    window.close()


def test_spotlight_hole_reveals_underlying_ui(qapp, tmp_path, monkeypatch) -> None:
    """Composition réelle de la fenêtre : à l'intérieur du spotlight, le
    pixel est EXACTEMENT celui de l'interface (ni noir, ni voile) — le trou
    laisse voir ce qui se trouve derrière le tutoriel. Vérifié sur la
    première étape (zone de dépôt) et sur une étape ciblant un petit
    bouton."""
    window, overlay, _ = _tutorial_window(qapp, tmp_path, monkeypatch)

    def check(step: int) -> None:
        overlay._index = step
        overlay._refresh()
        qapp.processEvents()
        target = overlay.spotlight_rect
        assert not target.isNull(), f"étape {step} : cible vide"
        c = target.center()
        with_veil = window.grab().toImage().pixelColor(c.x(), c.y())
        overlay.hide()
        qapp.processEvents()
        without_veil = window.grab().toImage().pixelColor(c.x(), c.y())
        overlay.show()
        qapp.processEvents()
        # Le trou révèle exactement l'interface derrière (pas de noir ajouté
        # par l'overlay).
        assert with_veil == without_veil, (
            f"étape {step} : l'intérieur du spotlight n'est pas transparent "
            f"({with_veil.name()} vs {without_veil.name()})"
        )

    # Étape 1 : la grande zone de dépôt.
    check(0)
    # Une étape ciblant une zone plus petite (Recherche + loupe).
    for step in range(overlay.step_count):
        if "search" in overlay._steps[step].get("title", ""):
            check(step)
            break
    window.close()


# ---------------------------------------------------------------------- #
# 1d. 1.3.13 — English langue par défaut d'une nouvelle installation
# ---------------------------------------------------------------------- #
def test_virgin_install_default_language_is_english(qapp, tmp_path, monkeypatch) -> None:
    """Aucune langue enregistrée → l'application démarre en **English**
    (défaut 1.3.13), tout en demandant quand même l'écran de langue."""
    from app.config import AppSettings
    from ui.main_window import MainWindow

    appdata, lib, fleasion, settings_path = _make_env(tmp_path, monkeypatch)
    assert "language" not in json.loads(settings_path.read_text(encoding="utf-8"))

    settings = AppSettings.load()
    assert settings.language == "en"
    assert settings.language_chosen is False  # l'écran de langue sera demandé

    fake = _FakeLangDialog("en")
    window = MainWindow()
    _install_language_factory(window, lambda parent=None: fake)
    _open(window, qapp)
    assert window.settings.language == "en"
    assert fake.calls == 1  # écran de langue bien demandé au premier lancement
    window.close()


def test_language_dialog_preselects_english_on_virgin_install(
    qapp, tmp_path, monkeypatch
) -> None:
    """Nouvelle installation : **English est sélectionné par défaut** dans
    l'écran de langue ; Français et toutes les autres langues restent
    disponibles."""
    from app.i18n import current_language, set_language
    from ui.views.language_dialog import LanguageDialog

    _make_env(tmp_path, monkeypatch)
    previous = current_language()
    try:
        set_language("en")  # état d'une installation vierge (aucune langue)
        dialog = LanguageDialog()
        assert dialog.selected_code == "en"
        codes = [dialog._list.item(i).data(Qt.UserRole)
                 for i in range(dialog._list.count())]
        assert codes == ["fr", "en", "es", "de", "it", "pt", "nl", "pl", "ru", "tr"]
        assert "fr" in codes and "de" in codes and "en" in codes
        dialog.close()
    finally:
        set_language(previous)


def test_choose_french_starts_tutorial_in_french(qapp, tmp_path, monkeypatch) -> None:
    """Choisir Français dans l'écran de langue : enregistré, et le tutoriel
    démarre dans la langue choisie (français)."""
    from ui.main_window import MainWindow

    appdata, lib, fleasion, settings_path = _make_env(tmp_path, monkeypatch)
    fake = _FakeLangDialog("fr")
    window = MainWindow()
    _install_language_factory(window, lambda parent=None: fake)
    _open(window, qapp)

    assert fake.calls == 1
    assert window.settings.language == "fr"
    payload = json.loads(settings_path.read_text(encoding="utf-8"))
    assert payload["language"] == "fr"  # langue choisie persistée
    assert window._onboarding_overlay is not None
    assert window._onboarding_overlay.bubble._title.text() == "Ajouter vos fichiers"
    window.close()


def test_existing_french_user_keeps_french(qapp, tmp_path, monkeypatch) -> None:
    """Un utilisateur ayant déjà enregistré ``fr`` reste en français :
    jamais re-demandé, jamais basculé sur l'anglais par la nouvelle valeur
    par défaut."""
    from ui.main_window import MainWindow

    appdata, lib, fleasion, settings_path = _make_env(tmp_path, monkeypatch,
                                                      language="fr", completed=True)
    window = MainWindow()
    _install_language_factory(window, _BoomLangDialog)  # écran jamais demandé
    _open(window, qapp)
    assert window.settings.language == "fr"
    assert window._onboarding_overlay is None
    window.close()


def test_reset_returns_virgin_install_with_english_default(
    qapp, tmp_path, monkeypatch
) -> None:
    """Reset du premier lancement : après relance, aucune langue choisie →
    English par défaut (le scénario vierge recommence)."""
    from app.config import AppSettings, settings_file

    appdata, lib, fleasion, settings_path = _make_env(tmp_path, monkeypatch,
                                                      language="de", completed=True)
    # Reset (variable de dev/test, jamais active par défaut).
    monkeypatch.setenv("RCM_RESET_ONBOARDING", "1")
    AppSettings.load()
    monkeypatch.delenv("RCM_RESET_ONBOARDING", raising=False)

    # Relance réelle : langue jamais choisie → English par défaut.
    payload = json.loads(settings_file().read_text(encoding="utf-8"))
    assert payload.get("language") is None  # langue réinitialisée
    reloaded = AppSettings.load()
    assert reloaded.language_chosen is False
    assert reloaded.onboarding_completed is False
    assert reloaded.language == "en"  # défaut English (1.3.13)
    # Rien d'autre n'a été supprimé.
    assert reloaded.library_dir == lib and reloaded.fleasion_dir == fleasion


# ---------------------------------------------------------------------- #
# 7. Editor Mode tutorial step
# ---------------------------------------------------------------------- #
def _editor_step_index(overlay) -> int | None:
    """Return the index of the Editor Mode step, or None."""
    for i, step in enumerate(overlay._steps):
        if "editor" in step.get("title", ""):
            return i
    return None


def test_editor_step_exists_and_has_translations(qapp, tmp_path, monkeypatch) -> None:
    """The Editor Mode tutorial step exists and its title/body are
    translated (never the raw key)."""
    from app.i18n import t

    window, overlay, _ = _tutorial_window(qapp, tmp_path, monkeypatch)
    idx = _editor_step_index(overlay)
    assert idx is not None, "Editor Mode step not found in tutorial"
    step = overlay._steps[idx]
    assert step["title"] == "onboarding.step_editor.title"
    assert step["body"] == "onboarding.step_editor.body"
    # Translations are non-empty and differ from the key.
    assert t(step["title"]) != step["title"]
    assert t(step["body"]) != step["body"]
    assert len(t(step["body"])) > 20  # body is descriptive, not empty
    window.close()


def test_editor_step_targets_real_editor_button(qapp, tmp_path, monkeypatch) -> None:
    """The Editor Mode step targets the real editor button widget (not a
    fixed pixel position). The spotlight geometry matches the button's
    real geometry."""
    window, overlay, _ = _tutorial_window(qapp, tmp_path, monkeypatch)
    idx = _editor_step_index(overlay)
    assert idx is not None
    overlay._index = idx
    overlay._refresh()
    qapp.processEvents()

    rect = overlay.target_rect(idx)
    assert not rect.isNull(), "Editor step has no valid target"
    # The real editor button exists and is visible.
    btn = window._editor_btn
    assert btn.isVisible()
    # The spotlight rect is computed from the button's real geometry
    # (with padding), not from any hardcoded value.
    btn_center = btn.mapToGlobal(btn.rect().center())
    spot_center = rect.center()
    assert abs(spot_center.x() - btn_center.x()) < 15, (
        f"Spotlight center {spot_center} not near button center {btn_center}"
    )
    assert abs(spot_center.y() - btn_center.y()) < 15
    # The spotlight encloses the button (with padding).
    btn_rect_in_overlay = QRect(
        overlay.mapFromGlobal(btn.mapToGlobal(btn.rect().topLeft())),
        overlay.mapFromGlobal(btn.mapToGlobal(btn.rect().bottomRight())),
    )
    assert rect.contains(btn_rect_in_overlay.center()), (
        "Spotlight does not contain the editor button center"
    )
    window.close()


def test_editor_step_spotlight_tracks_button_on_resize(qapp, tmp_path, monkeypatch) -> None:
    """After resizing the window, the editor step spotlight dynamically
    repositions to follow the real button geometry."""
    window, overlay, _ = _tutorial_window(qapp, tmp_path, monkeypatch)
    idx = _editor_step_index(overlay)
    assert idx is not None

    for size in [(960, 640), (1600, 900), (1280, 720)]:
        window.resize(*size)
        qapp.processEvents()
        qapp.processEvents()
        overlay._index = idx
        overlay._refresh()
        qapp.processEvents()

        btn = window._editor_btn
        btn_rect = btn.geometry()
        spotlight = overlay.target_rect(idx)
        # The spotlight center must be near the button center.
        btn_center = btn_rect.center()
        spot_center = spotlight.center()
        assert abs(spot_center.x() - btn_center.x()) < 30, (
            f"Spotlight x={spot_center.x()} != button x={btn_center.x()} at {size}"
        )
        assert abs(spot_center.y() - btn_center.y()) < 30, (
            f"Spotlight y={spot_center.y()} != button y={btn_center.y()} at {size}"
        )
    window.close()


def test_editor_step_between_search_and_settings(qapp, tmp_path, monkeypatch) -> None:
    """The Editor Mode step is positioned between Search and Settings in
    the tutorial sequence."""
    window, overlay, _ = _tutorial_window(qapp, tmp_path, monkeypatch)
    editor_idx = _editor_step_index(overlay)
    assert editor_idx is not None
    # The step before should be Search, the step after should be Settings.
    prev_title = overlay._steps[editor_idx - 1]["title"]
    next_title = overlay._steps[editor_idx + 1]["title"]
    assert "search" in prev_title, f"Step before editor is not search: {prev_title}"
    assert "settings" in next_title, f"Step after editor is not settings: {next_title}"
    window.close()


def test_editor_step_in_french(qapp, tmp_path, monkeypatch) -> None:
    """When the language is French, the editor step shows French text."""
    from app.i18n import current_language, set_language

    window, overlay, _ = _tutorial_window(qapp, tmp_path, monkeypatch)
    idx = _editor_step_index(overlay)
    assert idx is not None
    prev = current_language()
    try:
        set_language("fr")
        overlay.retranslate()
        qapp.processEvents()
        step = overlay._steps[idx]
        from app.i18n import t
        title_fr = t(step["title"])
        body_fr = t(step["body"])
        assert "Mode Éditeur" in title_fr or "diteur" in title_fr
        assert len(body_fr) > 20
    finally:
        set_language(prev)
    window.close()


def test_all_previous_steps_still_have_valid_targets(qapp, tmp_path, monkeypatch) -> None:
    """All 9 steps have valid targets and translations — regression check."""
    from app.i18n import t

    window, overlay, _ = _tutorial_window(qapp, tmp_path, monkeypatch)
    assert overlay.step_count == 9
    for i in range(overlay.step_count):
        rect = overlay.target_rect(i)
        assert not rect.isNull() and not rect.isEmpty(), f"Step {i}: invalid target"
        assert rect.left() >= 0 and rect.top() >= 0, f"Step {i}: target outside window"
        step = overlay._steps[i]
        assert t(step["title"]) != step["title"], f"Step {i}: untranslated title"
        assert t(step["body"]) != step["body"], f"Step {i}: untranslated body"
    window.close()
