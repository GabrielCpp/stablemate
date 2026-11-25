"""Ask a backend CLI for the public full-session export of a turn."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable


def opencode_export(session_id: str) -> bytes | None:
    """OpenCode's public full-session export, including reasoning and tool parts."""
    for _attempt in range(2):
        try:
            result = subprocess.run(
                ["opencode", "export", session_id],
                capture_output=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        try:
            loaded = json.loads(result.stdout)
        except ValueError:
            continue
        if isinstance(loaded, dict):
            return result.stdout
    return None


EXPORTERS: dict[str, Callable[[str], bytes | None]] = {
    "opencode": opencode_export,
}


def export_session(backend: str, session_id: str) -> bytes | None:
    """A backend's public full-session export, or ``None`` when unavailable."""
    exporter = EXPORTERS.get(backend)
    if exporter is None:
        return None
    try:
        return exporter(session_id)
    except OSError:
        return None


def probe_exporters(session_id: str) -> tuple[str, bytes | None]:
    """Which public backend exporter recognizes ``session_id``, if any."""
    for backend in EXPORTERS:
        exported = export_session(backend, session_id)
        if exported is not None:
            return backend, exported
    return "", None
