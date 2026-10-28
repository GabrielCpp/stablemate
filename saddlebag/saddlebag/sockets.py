"""Where the daemon's unix socket lives, computed with nothing heavier than the standard library."""

from __future__ import annotations

import os
from pathlib import Path

SOCKET_FILE = "saddlebag.sock"

_SUN_PATH_MAX = 100


def socket_path() -> Path:
    """Where the daemon listens, shortened when the natural path would not fit a unix socket."""
    explicit = os.environ.get("SADDLEBAG_SOCKET")
    if explicit:
        return fit_socket_path(Path(explicit))
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    if runtime:
        return fit_socket_path(Path(runtime) / SOCKET_FILE)
    import platformdirs

    base = Path(platformdirs.user_runtime_dir("saddlebag"))
    return fit_socket_path(base / SOCKET_FILE)


def fit_socket_path(path: Path) -> Path:
    """``path`` itself, or a short temp path derived from it when it exceeds sun_path."""
    if len(str(path)) <= _SUN_PATH_MAX:
        return path
    import hashlib
    import tempfile

    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    return Path(tempfile.gettempdir()) / f"saddlebag-{digest}.sock"
