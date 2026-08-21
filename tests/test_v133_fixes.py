"""v1.3.3 regression tests — distributable EXE + first-run folder selection.

Covers the fixes for the release whose single question is: *can I send the
.exe to someone who never used the app and let them pick their own folders
without a crash?*

* path normalization (trailing separators, slashes, env vars, relative);
* library validation before saving/scanning (missing, not-a-folder, empty,
  spaces, deeply nested, real categories);
* invalid selection never changes the saved settings and shows an error;
* a valid selection scans off the GUI thread (window stays responsive);
* settings live in APPDATA — never the working directory (System32);
* the global exception hook is installed and idempotent.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from app.config import AppSettings, normalize_path
from app.scanner import scan_library, validate_library_root


# ---------------------------------------------------------------------- #
# Fixtures
# ---------------------------------------------------------------------- #
@pytest.fixture
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _configure(appdata: Path, library: Path, fleasion: Path) -> None:
    """Write the settings.json the app reads on startup (like test_smoke)."""
    settings_path = appdata / "RivalsConfigManager" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps({"library_dir": str(library), "fleasion_dir": str(fleasion)}),
        encoding="utf-8",
    )
    fleasion.mkdir(parents=True, exist_ok=True)


def _real_library(root: Path) -> Path:
    """A library with real categories (Scenario H)."""
    lib = root / "Rivals Configs"
    (lib / "Charms").mkdir(parents=True)
    (lib / "Charms" / "nemesis charm.json").write_text(
        '{"replacement_rules": []}', encoding="utf-8"
    )
    (lib / "rivals skins" / "Primary" / "Assault Rifle").mkdir(parents=True)
    (lib / "rivals skins" / "Primary" / "Assault Rifle" / "ak-47.json").write_text(
        '{"replacement_rules": []}', encoding="utf-8"
    )
    return lib


def _wait_for_scan(window, qapp, timeout: float = 10.0) -> None:
    """Process events until the background scan thread has finished."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        thread = window._scan_thread
        if thread is None or not thread.isRunning():
            break
        time.sleep(0.01)
    qapp.processEvents()


# ---------------------------------------------------------------------- #
# 1. normalize_path
# ---------------------------------------------------------------------- #
def test_normalize_path_trailing_separators_and_slashes() -> None:
    # Windows path with a trailing backslash + mixed slashes.
    assert normalize_path(r"C:\Users\Test User\Desktop\Rivals Configs\\") == Path(
        r"C:\Users\Test User\Desktop\Rivals Configs"
    )
    assert normalize_path("C:/Users/Test User/Desktop/Rivals Configs/") == Path(
        "C:/Users/Test User/Desktop/Rivals Configs"
    )


def test_normalize_path_expands_home_and_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("RC_LIB", str(tmp_path / "lib"))
    assert normalize_path("%RC_LIB%") == Path(tmp_path / "lib")
    home = Path.home()
    assert normalize_path("~") == home


def test_normalize_path_makes_relative_absolute(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert normalize_path("sub") == Path(tmp_path / "sub")


# ---------------------------------------------------------------------- #
# 2. validate_library_root
# ---------------------------------------------------------------------- #
def test_validate_missing_folder(tmp_path: Path) -> None:
    errors = validate_library_root(tmp_path / "does-not-exist")
    assert errors, "a missing folder must be reported"


def test_validate_not_a_folder(tmp_path: Path) -> None:
    file = tmp_path / "file.txt"
    file.write_text("x", encoding="utf-8")
    assert validate_library_root(file)


def test_validate_empty_folder_is_valid(tmp_path: Path) -> None:
    empty = tmp_path / "Empty Library"
    empty.mkdir()
    assert validate_library_root(empty) == []


def test_validate_folder_with_spaces(tmp_path: Path) -> None:
    lib = tmp_path / "Test User" / "Rivals Configs"
    lib.mkdir(parents=True)
    assert validate_library_root(lib) == []


def test_validate_deeply_nested(tmp_path: Path) -> None:
    lib = tmp_path / "Test User" / "Documents" / "Projects" / "Rivals" / "Rivals Configs"
    lib.mkdir(parents=True)
    assert validate_library_root(lib) == []


# ---------------------------------------------------------------------- #
# 3. scan_library: no crash on every first-run scenario
# ---------------------------------------------------------------------- #
def test_scan_empty_library_ok(tmp_path: Path) -> None:
    empty = tmp_path / "Empty"
    empty.mkdir()
    result = scan_library(empty)
    assert result.ok and result.node is not None


def test_scan_library_with_spaces(tmp_path: Path) -> None:
    lib = _real_library(tmp_path / "Test User")
    result = scan_library(lib)
    assert result.ok
    assert any(s.name == "Charms" for s in result.node.subdirs)


def test_scan_deeply_nested_library(tmp_path: Path) -> None:
    lib = _real_library(tmp_path / "Test User" / "Documents" / "Projects" / "Rivals")
    result = scan_library(lib)
    assert result.ok
    assert any(s.name == "Charms" for s in result.node.subdirs)


def test_scan_invalid_path_returns_errors_not_exception(tmp_path: Path) -> None:
    result = scan_library(tmp_path / "missing")
    assert not result.ok
    assert result.errors


# ---------------------------------------------------------------------- #
# 4. Settings must live in APPDATA — never the working directory
# ---------------------------------------------------------------------- #
def test_settings_in_appdata_even_with_system32_cwd(tmp_path: Path, monkeypatch) -> None:
    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    # Simulate a launcher that set the working directory to System32.
    fake_system32 = tmp_path / "System32"
    fake_system32.mkdir()
    monkeypatch.chdir(fake_system32)

    settings = AppSettings()
    settings.library_dir = Path("C:/Lib")
    settings.fleasion_dir = Path("C:/Fleasion")
    settings.save()

    from app.config import settings_file

    assert settings_file().is_relative_to(appdata)
    # Nothing was written next to the program (the simulated System32 cwd).
    assert not (fake_system32 / "settings.json").exists()
    assert not (fake_system32 / "RivalsConfigManager").exists()


# ---------------------------------------------------------------------- #
# 5. Global exception hook
# ---------------------------------------------------------------------- #
def test_excepthook_installed_and_idempotent() -> None:
    import sys

    from app import errors

    original = sys.excepthook
    try:
        errors._installed = False
        errors.install_excepthook()
        assert sys.excepthook is errors._handle
        # Installing again must not stack the hook.
        errors.install_excepthook()
        assert sys.excepthook is errors._handle
    finally:
        sys.excepthook = original
        errors._installed = False


# ---------------------------------------------------------------------- #
# 6. _set_library_dir: validate before saving, scan off the GUI thread
# ---------------------------------------------------------------------- #
def test_set_library_dir_rejects_invalid_path_without_saving(
    tmp_path: Path, qapp, monkeypatch
) -> None:
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    lib = _real_library(tmp_path)
    _configure(appdata, lib, tmp_path / "fleasion")

    window = MainWindow()
    window.show()
    qapp.processEvents()
    original = window.settings.library_dir

    # Select a non-existent folder: it must be refused, settings untouched.
    window._set_library_dir(tmp_path / "does-not-exist")
    qapp.processEvents()

    assert window.settings.library_dir == original
    # The on-screen label is reverted to the still-saved path.
    assert window._settings._library_path.text() == str(original)
    window.deleteLater()


def test_set_library_dir_valid_path_scans_in_background(
    tmp_path: Path, qapp, monkeypatch
) -> None:
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    lib = _real_library(tmp_path)
    _configure(appdata, lib, tmp_path / "fleasion")

    window = MainWindow()
    window.show()
    qapp.processEvents()

    new_lib = _real_library(tmp_path / "other")
    window._set_library_dir(new_lib)
    qapp.processEvents()

    # The scan runs off the GUI thread; wait for it to finish.
    _wait_for_scan(window, qapp)

    assert window.settings.library_dir == new_lib
    assert window.root_node is not None
    assert any(s.name == "Charms" for s in window.root_node.subdirs)
    window.deleteLater()


def test_set_library_dir_empty_folder_scans_ok(tmp_path: Path, qapp, monkeypatch) -> None:
    from ui.main_window import MainWindow

    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    lib = _real_library(tmp_path)
    _configure(appdata, lib, tmp_path / "fleasion")

    window = MainWindow()
    window.show()
    qapp.processEvents()

    empty = tmp_path / "Empty Library"
    empty.mkdir()
    window._set_library_dir(empty)
    _wait_for_scan(window, qapp)

    assert window.settings.library_dir == empty
    assert window.root_node is not None  # an empty folder is a valid library
    assert window.root_node.total_items() == 0
    window.deleteLater()


# ---------------------------------------------------------------------- #
# 7. The browse dialog never starts from an empty/cwd directory
# ---------------------------------------------------------------------- #
def test_browse_uses_home_when_no_current_path(tmp_path: Path, qapp, monkeypatch) -> None:
    from PySide6.QtWidgets import QFileDialog

    from ui.views.settings_view import SettingsView

    view = SettingsView()
    captured: dict = {}

    def fake_get_existing_dir(parent=None, caption="", dir="", options=None):
        captured["dir"] = dir
        return str(tmp_path / "Selected Folder")

    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(fake_get_existing_dir)
    )
    # No path configured yet: the label is "—", so the dialog must start
    # from the user's home folder, never "" (which Qt maps to the cwd).
    view._browse("library")

    assert captured["dir"] == str(Path.home())
    assert view._library_path.text() == str(normalize_path(tmp_path / "Selected Folder"))
    view.deleteLater()


# ---------------------------------------------------------------------- #
# 8. Asset sync: the button is present and a no-remote run never crashes
# ---------------------------------------------------------------------- #
def test_asset_sync_no_remote_is_safe(tmp_path: Path, qapp, monkeypatch) -> None:
    from ui.main_window import MainWindow

    monkeypatch.setenv("RCM_ASSET_BASE_URL", "")
    appdata = tmp_path / "AppData" / "Roaming"
    appdata.mkdir(parents=True)
    monkeypatch.setenv("APPDATA", str(appdata))
    lib = _real_library(tmp_path)
    _configure(appdata, lib, tmp_path / "fleasion")

    window = MainWindow()
    window.show()
    qapp.processEvents()

    # v1.3.5 : la synchronisation des ressources est un outil
    # d'administration des assets — invisible dans la version normale
    # (porte centrale ``ADMIN_MODE``), le mécanisme reste intact.
    assert window._settings._sync_assets_btn is not None
    assert "es ressources" in window._settings._sync_assets_btn.text() or \
        "resources" in window._settings._sync_assets_btn.text().lower()
    assert not window._settings._sync_assets_btn.isVisible()

    # Triggering a sync with no remote configured is a clean no-op.
    window._sync_assets(silent=False)
    qapp.processEvents()
    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        qapp.processEvents()
        worker = window._asset_sync_worker
        if worker is None or not worker.isRunning():
            break
        time.sleep(0.01)
    qapp.processEvents()
    assert window.root_node is not None  # the app keeps working normally
    window.deleteLater()
