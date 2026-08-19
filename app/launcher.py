"""Application entry point (used by main.py)."""

from __future__ import annotations

import logging
import sys


def run() -> int:
    from PySide6.QtWidgets import QApplication

    from ui.main_window import MainWindow
    from ui.theme import apply_theme

    app = QApplication(sys.argv)
    app.setApplicationName("Rivals Config Manager")
    app.setOrganizationName("RivalsConfigManager")

    apply_theme(app)

    window = MainWindow()
    window.show()
    return app.exec()
