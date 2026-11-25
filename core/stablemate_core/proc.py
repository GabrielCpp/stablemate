"""Whether a process runs on this host and which process a pid names, on Linux, macOS, BSD and Windows."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_STILL_ACTIVE = 259
_ACCESS_DENIED = 5


def _platform() -> str:
    return sys.platform


def _linux_stat(pid: int) -> list[str] | None:
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="ascii", errors="replace")
    except OSError:
        return None
    return text.rpartition(")")[2].split()


def _ps(field: str, pid: int) -> str | None:
    try:
        done = subprocess.run(
            ["ps", "-o", f"{field}=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def _windows_alive(pid: int) -> bool:
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return kernel32.GetLastError() == _ACCESS_DENIED
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return kernel32.GetLastError() == _ACCESS_DENIED
        return code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _windows_start_token(pid: int) -> str:
    if sys.platform != "win32":
        return ""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.windll.kernel32
    kernel32.OpenProcess.restype = wintypes.HANDLE
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
        ok = kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        )
        if not ok:
            return ""
        return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
    finally:
        kernel32.CloseHandle(handle)


def pid_alive(pid: int) -> bool:
    """Whether *pid* names a running process, a zombie not counting as running."""
    if pid <= 0:
        return False
    platform = _platform()
    if platform == "win32":
        return _windows_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    except OSError:
        return False
    if platform == "linux":
        fields = _linux_stat(pid)
        return fields is None or not fields or fields[0] != "Z"
    state = _ps("stat", pid)
    return state is None or not state.startswith("Z")


def pid_start_token(pid: int) -> str:
    """A string that changes when the OS reuses *pid* for another process, empty where the process is gone or unreadable."""
    if pid <= 0:
        return ""
    platform = _platform()
    if platform == "win32":
        return _windows_start_token(pid)
    if platform == "linux":
        fields = _linux_stat(pid)
        return fields[19] if fields and len(fields) > 19 else ""
    return _ps("lstart", pid) or ""
