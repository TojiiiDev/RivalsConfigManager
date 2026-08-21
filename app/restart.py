"""« Recharger l'application » (v1.3.5) — true application relaunch.

A real restart, never a widget refresh: the running instance saves its
state, spawns a fresh instance and then exits. The relaunch command line
never depends on the working directory — it uses the real interpreter /
executable paths resolved once at startup:

* **Frozen build** (PyInstaller ``.exe``): the executable itself
  (``sys.executable``), wherever it was launched from — shortcut,
  desktop, any folder.
* **Source run** (``python main.py``): the interpreter + the absolute
  path of the entry script (captured at import time, so the cwd at click
  time is irrelevant).

The module is pure Python (no Qt) so it can be unit-tested directly.
"""

from __future__ import annotations

import os
import subprocess
import sys

#: Absolute path of the script that started this process, captured at
#: import time. ``sys.argv[0]`` may be relative to the launch folder; the
#: absolute form is resolved here once, so the relaunch never depends on
#: the current working directory at click time.
_ENTRY_SCRIPT = os.path.abspath(sys.argv[0])


def relaunch_command(script: str | None = None) -> list[str]:
    """The command line that restarts the application.

    * Frozen build (``.exe``): ``[sys.executable]`` — the exe itself.
    * Source run: ``[sys.executable, <absolute entry script>]`` — the
      script path captured at startup, never the cwd.

    ``script`` overrides the entry script (used by tests); when ``None``,
    the script that started the process is used. Never references
    ``System32`` or any environment-specific folder: the interpreter and
    the script are both real, absolute paths.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable]
    target = os.path.abspath(script) if script is not None else _ENTRY_SCRIPT
    return [sys.executable, target]


def relaunch(script: str | None = None) -> subprocess.Popen | None:
    """Spawn the fresh instance and return its :class:`subprocess.Popen`.

    The caller (main window) is expected to save its state BEFORE calling
    this, then exit immediately after. Returns ``None`` when the process
    could not be started — the caller keeps running and shows an error.
    """
    try:
        return subprocess.Popen(relaunch_command(script))
    except OSError:
        return None
