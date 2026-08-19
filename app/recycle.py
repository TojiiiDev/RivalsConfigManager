"""Move files/folders to the **Windows Recycle Bin** (recoverable).

This is the only way destructive operations may proceed: files are moved
to the Recycle Bin with ``SHFileOperationW(FO_DELETE | FOF_ALLOWUNDO)``,
never deleted permanently with ``os.remove`` / ``shutil.rmtree``.

On failure — or on a non-Windows system — :class:`OSError` is raised and
the caller must stop, never fall back to a silent permanent deletion.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

from .i18n import t


class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("wFunc", wintypes.UINT),
        ("pFrom", wintypes.LPCWSTR),
        ("pTo", wintypes.LPCWSTR),
        ("fFlags", wintypes.WORD),
        ("fAnyOperationsAborted", wintypes.BOOL),
        ("hNameMappings", wintypes.LPVOID),
        ("lpszProgressTitle", wintypes.LPCWSTR),
    ]


_FO_DELETE = 0x0003
#: Move to the Recycle Bin instead of deleting permanently.
_FOF_ALLOWUNDO = 0x0040
_FOF_NOCONFIRMATION = 0x0010
_FOF_SILENT = 0x0004
_FOF_NOERRORUI = 0x0400


def move_to_recycle_bin(path: Path) -> None:
    """Move a file or folder to the Windows Recycle Bin (recoverable).

    Raises :class:`OSError` when the move fails or on non-Windows systems.
    A missing path is a no-op.
    """
    target = Path(path)
    if not target.exists():
        return
    if sys.platform != "win32":
        raise OSError(t("recycle.not_available"))

    # SHFileOperationW expects a double-null-terminated source list.
    source = str(target.resolve()) + "\0"
    ops = _SHFILEOPSTRUCTW()
    ops.hwnd = None
    ops.wFunc = _FO_DELETE
    ops.pFrom = source
    ops.pTo = None
    ops.fFlags = _FOF_ALLOWUNDO | _FOF_NOCONFIRMATION | _FOF_SILENT | _FOF_NOERRORUI

    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(ops))
    if result != 0 or ops.fAnyOperationsAborted:
        raise OSError(
            t("recycle.move_failed", name=target.name, error=result)
        )
