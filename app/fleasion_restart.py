"""Controlled restart of the running Fleasion process.

Diagnostic findings (real machine, Fleasion v2.1.0):

* Fleasion is a Python + PyQt6 application packaged as a PyInstaller
  one-file exe. It loads ``enabled_configs`` from ``settings.json`` **only
  when its state is initialised** — there is no watchdog / FileSystemWatcher
  on ``settings.json`` and no IPC / named pipe / control port. Editing the
  file while Fleasion is running has **no** visible effect (proven by the
  user's real test: the checkbox stayed unchecked).
* A manual click in Fleasion's UI calls its own internal handler which
  updates memory, writes ``settings.json`` and logs
  ``[Config] Enabled: X`` / ``[Config] Disabled: X``.
* At startup Fleasion logs one ``[Config] Enabled: X`` line per enabled
  configuration (observed burst: Keyper, Keytana, Pixelhandgun (1), ...).

Therefore the only reliable way to make a *running* Fleasion pick up a new
selection is to **close it cleanly, (re)write settings.json, relaunch it**
and **verify through Fleasion's own log** that the configuration was loaded
(``[Config] Enabled: <name>``). No fake success: without that log line the
activation is reported as unconfirmed.

This module is stdlib-only (subprocess + PowerShell CIM + tasklist/taskkill)
so it does not add dependencies. All helpers are small and monkeypatchable
for tests.
"""

from __future__ import annotations

import json
import shlex
import subprocess
import time
from pathlib import Path

#: Matched in the image name / command line of Fleasion processes.
_PROCESS_MARKER = "fleasion"

#: Log line prefix Fleasion writes when a configuration is loaded/enabled.
_ENABLED_MARKER = "[Config] Enabled:"

#: Image names that can never be Fleasion (they appear only because the
#: query itself contains the literal "fleasion" in its command line).
_SKIP_IMAGES = frozenset({
    "powershell.exe", "pwsh.exe", "bash.exe", "sh.exe", "dash.exe",
    "cmd.exe", "conhost.exe", "python.exe", "pythonw.exe",
    "taskkill.exe", "tasklist.exe", "wmic.exe", "timeout.exe", "git.exe",
})

#: PowerShell script enumerating processes whose *image name* or command
#: line mentions Fleasion. The real Fleasion (one-file PyInstaller build)
#: exposes its image name but an empty ExecutablePath and CommandLine, so
#: the image name is the reliable signal. UTF-8 output is forced so
#: non-ASCII paths survive the pipe.
_PS_FIND_PROCESSES = (
    "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
    "$p = Get-CimInstance Win32_Process | "
    "Where-Object { $_.ProcessId -ne $PID -and "
    "($_.Name -match 'fleasion' -or ($_.CommandLine -and ($_.CommandLine -match 'fleasion'))) } | "
    "ForEach-Object { "
    "[PSCustomObject]@{ pid = $_.ProcessId; name = $_.Name; exe = $_.ExecutablePath; cmd = $_.CommandLine } "
    "}; "
    "if ($p) { $p | ConvertTo-Json -Compress }"
)

_GRACEFUL_WAIT = 8.0   # seconds to wait after WM_CLOSE before forcing
_FORCE_WAIT = 5.0      # seconds to wait after /F before giving up
_POLL_INTERVAL = 0.5   # seconds between liveness/log polls


# ---------------------------------------------------------------------- #
def find_fleasion_processes() -> list[dict] | None:
    """Locate running Fleasion processes.

    Returns a list of ``{"pid": int, "exe": str | None, "cmd": str | None}``
    or ``None`` when the enumeration itself failed (unknown state — callers
    must not assume Fleasion is running in that case).
    """
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_FIND_PROCESSES],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    out = (proc.stdout or "").strip()
    if not out:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return None

    processes: list[dict] = []
    for row in data:
        pid = row.get("pid")
        if not isinstance(pid, int):
            continue
        name = row.get("name") or None
        exe = row.get("exe") or None
        cmd = row.get("cmd") or None
        if not exe and cmd:
            # One-file PyInstaller executables sometimes expose an empty
            # ExecutablePath; the real exe is the first token of the
            # command line.
            try:
                tokens = shlex.split(cmd)
            except ValueError:
                tokens = []
            if tokens and tokens[0].lower().endswith(".exe"):
                exe = tokens[0]
        if not exe and name and name.lower().endswith(".exe"):
            # Elevated one-file build: image name only. The full path is
            # resolved afterwards (profile search for the exact name).
            exe = name
        # Reject candidates that are not Fleasion: shells and interpreters
        # only matched because the query's own command line contains the
        # literal "fleasion" marker.
        if not exe or not _looks_like_fleasion(exe):
            continue
        resolved = _resolve_exe_path(exe, name, cmd)
        processes.append({"pid": int(pid), "exe": resolved, "name": name, "cmd": cmd})
    return processes


def _looks_like_fleasion(exe: str) -> bool:
    """True when the candidate really is a Fleasion executable (never a
    shell/interpreter matched by the query itself)."""
    lowered = exe.lower()
    if not lowered.endswith(".exe"):
        return False
    if Path(lowered).name in _SKIP_IMAGES:
        return False
    return "fleasion" in lowered


def _resolve_exe_path(exe: str, name: str | None, cmd: str | None) -> str | None:
    """Return a launchable path for the Fleasion executable, or None.

    Preference order: existing path (from ExecutablePath or the first
    command-line token) → user-profile search for the exact image name
    (the elevated one-file build hides its path)."""
    candidate = exe
    if Path(candidate).is_file():
        return str(Path(candidate))
    image_name = Path(exe).name
    found = _search_user_profile(image_name)
    if found is not None:
        return str(found)
    # Last resort: the first token of the command line may be a full path
    # even when the image name differs.
    if cmd:
        try:
            tokens = shlex.split(cmd)
        except ValueError:
            tokens = []
        if tokens and Path(tokens[0]).is_file():
            return str(Path(tokens[0]))
    return None


def _search_user_profile(image_name: str) -> Path | None:
    """Bounded search of the user profile for the exact exe name (Desktop,
    Downloads, LOCALAPPDATA + one sub-level). Never a system-wide search."""
    import os

    home = Path(os.path.expanduser("~"))
    bases = [
        home / "Desktop",
        home / "Downloads",
        Path(os.environ.get("LOCALAPPDATA", "")) if os.environ.get("LOCALAPPDATA") else None,
    ]
    for base in bases:
        if base is None or not base.is_dir():
            continue
        direct = base / image_name
        if direct.is_file():
            return direct
        try:
            for child in base.iterdir():
                if child.is_dir() and (child / image_name).is_file():
                    return child / image_name
        except OSError:
            continue
    return None


# ---------------------------------------------------------------------- #
def _pids_alive(pids: list[int]) -> bool:
    """True when at least one of the PIDs is still running."""
    for pid in pids:
        try:
            proc = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if str(pid) in (proc.stdout or ""):
            return True
    return False


def close_fleasion(pids: list[int], graceful_wait: float = _GRACEFUL_WAIT) -> bool:
    """Close Fleasion cleanly, escalating to a forced kill if needed.

    First a graceful ``taskkill`` (WM_CLOSE) is sent to each process; the
    process is given ``graceful_wait`` seconds to exit. If it is still
    alive, ``taskkill /F`` is used as a fallback. Returns True only when
    every PID is gone.
    """
    if not pids:
        return True
    try:
        for pid in pids:
            subprocess.run(
                ["taskkill", "/PID", str(pid)],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired):
        pass

    deadline = time.monotonic() + graceful_wait
    while time.monotonic() < deadline:
        if not _pids_alive(pids):
            return True
        time.sleep(_POLL_INTERVAL)

    for pid in pids:
        try:
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass
    deadline = time.monotonic() + _FORCE_WAIT
    while time.monotonic() < deadline:
        if not _pids_alive(pids):
            return True
        time.sleep(_POLL_INTERVAL)
    return not _pids_alive(pids)


# ---------------------------------------------------------------------- #
def start_fleasion(exe: Path) -> bool:
    """Launch Fleasion detached from the manager process."""
    try:
        subprocess.Popen(
            [str(exe)],
            cwd=str(exe.parent),
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
        )
        return True
    except OSError:
        return False


# ---------------------------------------------------------------------- #
def wait_for_log_event(
    log_path: Path,
    offset: int,
    needles: list[str],
    timeout: float = 25.0,
    interval: float = _POLL_INTERVAL,
) -> list[str]:
    """Wait for new log lines containing any needle (case-insensitive).

    Reads only the bytes written after ``offset`` and returns the matching
    lines as soon as one appears (or an empty list after ``timeout``).
    Handles a rotated/truncated log by falling back to reading the whole
    file.
    """
    deadline = time.monotonic() + timeout
    matched: list[str] = []
    seen: set[str] = set()
    current_offset = offset
    while time.monotonic() < deadline:
        try:
            size = log_path.stat().st_size
        except OSError:
            size = 0
        if size < current_offset:
            current_offset = 0  # log rotated or truncated: read everything
        try:
            with open(log_path, "rb") as fh:
                fh.seek(current_offset)
                new_bytes = fh.read()
            current_offset += len(new_bytes)
        except OSError:
            new_bytes = b""
        if new_bytes:
            text = new_bytes.decode("utf-8", errors="replace")
            for line in text.splitlines():
                lowered = line.lower()
                if any(needle.lower() in lowered for needle in needles) and line not in seen:
                    matched.append(line)
                    seen.add(line)
            if matched:
                return matched
        time.sleep(interval)
    return matched
