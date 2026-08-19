# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification.

Build the standalone Windows executable with:

    pyinstaller RivalsConfigManager.spec --noconfirm

Output: dist\\RivalsConfigManager.exe (single file, no Python required).
"""

import re
from pathlib import Path

from PyInstaller.utils.win32.versioninfo import (
    FixedFileInfo,
    StringFileInfo,
    StringStruct,
    StringTable,
    VarFileInfo,
    VarStruct,
    VSVersionInfo,
)

PROJECT_ROOT = Path(SPECPATH)

#: Application version — single source of truth: ``app/__init__.py``.
#: Read at build time so the Windows version resource can never drift.
_INIT = (PROJECT_ROOT / "app" / "__init__.py").read_text(encoding="utf-8")
_MATCH = re.search(r'__version__\s*=\s*"([^"]+)"', _INIT)
assert _MATCH is not None, "app/__init__.py doit définir __version__"
VERSION = _MATCH.group(1)
_VER = tuple(int(p) for p in VERSION.split("."))
_VER_FULL = _VER + (0,) * (4 - len(_VER))  # (major, minor, patch, build)

a = Analysis(
    ["main.py"],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # Runtime translation resources (i18n): bundled so the .exe never
        # depends on the source tree to find fr.json / en.json. Resolved at
        # runtime through sys._MEIPASS (app/i18n/manager.py).
        (
            str(PROJECT_ROOT / "app" / "i18n" / "translations"),
            "app/i18n/translations",
        ),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Heavy Qt modules the application never uses — keeps the .exe smaller.
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtWebEngineQuick",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtQml",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
        "PySide6.Qt3DExtras",
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtBluetooth",
        "PySide6.QtNfc",
        "PySide6.QtPositioning",
        "PySide6.QtSensors",
        "PySide6.QtSerialPort",
        "PySide6.QtSql",
        "tkinter",
        "unittest",
        "pydoc",
        "pdb",
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="RivalsConfigManager",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # windowed application (no terminal)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=_VER_FULL,
            prodvers=_VER_FULL,
            mask=0x3F,
            flags=0x0,
            OS=0x40004,
            fileType=0x1,
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo(
                [
                    StringTable(
                        "040904B0",
                        [
                            StringStruct("CompanyName", "RivalsConfigManager"),
                            StringStruct("FileDescription", "Rivals Config Manager"),
                            StringStruct("FileVersion", VERSION),
                            StringStruct("InternalName", "RivalsConfigManager"),
                            StringStruct("OriginalFilename", "RivalsConfigManager.exe"),
                            StringStruct("ProductName", "Rivals Config Manager"),
                            StringStruct("ProductVersion", VERSION),
                        ],
                    )
                ]
            ),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    ),
    icon=str(PROJECT_ROOT / "assets" / "icon.ico"),
)
