"""Rivals Config Manager — entry point.

Run the application from source with:

    python main.py

Build a standalone Windows executable with:

    pyinstaller RivalsConfigManager.spec
"""

from __future__ import annotations

import logging
import sys

from app.config import data_dir
from app.errors import install_excepthook
from app.launcher import run

# ---- Logging ----------------------------------------------------------- #
# Logs go to a file inside the per-user data folder so they never depend on
# where the program was launched from (useful when packaged as an .exe).
_LOG_FILE = data_dir() / "app.log"

# In a frozen *windowed* build (console=False) PyInstaller sets sys.stdout
# and sys.stderr to None: attaching a StreamHandler to a None stream would
# break every log emit. Only add a console handler when a real stream exists.
_handlers: list[logging.Handler] = [
    logging.FileHandler(_LOG_FILE, encoding="utf-8"),
]
if sys.stdout is not None:
    _handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    handlers=_handlers,
)
logger = logging.getLogger("main")
logger.info("Démarrage de Rivals Config Manager")

# Any unhandled exception is logged and shown instead of a silent crash.
install_excepthook()


if __name__ == "__main__":
    sys.exit(run())
