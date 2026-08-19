"""Global exception handling — never a silent crash.

A Windows GUI application must never die without a trace or a message. This
module installs a process-wide ``sys.excepthook`` that:

* writes the full traceback to the application log
  (``%APPDATA%\\RivalsConfigManager\\app.log``), so the problem is always
  diagnosable even on a machine without a console;
* shows a clear, dismissible message box when the error happens on the GUI
  thread, so the user knows something went wrong and can keep using the app
  (first-run folder-selection errors must never look like a crash);
* falls back to the interpreter's default hook afterwards.

The hook is deliberately idempotent: installing it twice is a no-op, so it
can be called from both ``main.py`` and ``app.launcher`` without surprises.
"""

from __future__ import annotations

import logging
import sys
import traceback

logger = logging.getLogger("app.errors")

#: Installed flag — the hook must never be stacked twice.
_installed = False


def _is_gui_thread() -> bool:
    """True when the current thread is the Qt main (GUI) thread.

    Showing a modal dialog from a non-GUI thread is not allowed by Qt, so
    background errors are only logged (never shown) — the GUI itself must
    surface its own failures through signals/toasts.
    """
    try:
        from PySide6.QtCore import QThread
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return False
        return QThread.currentThread() is app.thread()
    except Exception:  # pragma: no cover - defensive
        return False


def _show_error_box(detail: str) -> None:
    """Show a clear, non-crashing error dialog (GUI thread only)."""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox

        app = QApplication.instance()
        if app is None:
            return
        box = QMessageBox()
        box.setWindowTitle("Rivals Config Manager")
        box.setIcon(QMessageBox.Critical)
        box.setText("Une erreur inattendue est survenue.")
        box.setInformativeText(
            "Le détail a été écrit dans le journal de l'application. "
            "Vous pouvez continuer à utiliser l'application."
        )
        box.setDetailedText(detail)
        # A blocking box would freeze the thread that raised; keep it modal
        # but safe (only ever shown on the GUI thread).
        box.exec()
    except Exception:  # pragma: no cover - never raise from the hook
        pass


def _handle(exc_type, exc, tb) -> None:
    """Log the traceback, inform the user, then chain to the default hook."""
    detail = "".join(traceback.format_exception(exc_type, exc, tb))
    try:
        logger.critical("Erreur non gérée :\n%s", detail)
    except Exception:  # pragma: no cover - logging must never re-raise
        pass
    if _is_gui_thread():
        _show_error_box(detail)
    sys.__excepthook__(exc_type, exc, tb)


def install_excepthook() -> None:
    """Install the global exception hook (idempotent)."""
    global _installed
    if _installed:
        return
    _installed = True
    sys.excepthook = _handle
