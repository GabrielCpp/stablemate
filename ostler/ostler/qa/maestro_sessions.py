"""Retire the session records a Maestro CLI killed while it was starting leaves in its store."""

from __future__ import annotations

import os
import time
from pathlib import Path

HEARTBEAT_S = 5.0
"""How often a live Maestro CLI rewrites its own record's timestamp."""

SESSION_STORE = Path.home() / ".maestro" / "sessions"
"""Maestro's session store: one `<platform>_<session id>=<epoch ms>` line per CLI, no trailing newline."""

RETIRE_WAIT_S = 2 * HEARTBEAT_S + 2.0


def retire_dead_sessions(store: Path = SESSION_STORE, wait: float = RETIRE_WAIT_S) -> list[str]:
    """Drop every record in `store` whose timestamp does not advance within `wait` seconds.

    A Maestro CLI treats any record younger than 21 seconds as another CLI that owns the device
    driver, and then skips starting its own, so a record whose CLI died while it was still
    starting refuses every CLI that follows it until the record ages out. The CLI heartbeats its
    record every `HEARTBEAT_S`, so a record that stays put for two beats belongs to no process.
    Returns the keys it dropped.
    """
    before = _read(store)
    if not before:
        return []
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        time.sleep(0.25)
        now = _read(store)
        if all(key in now and now[key] != stamp for key, stamp in before.items()):
            return []
    now = _read(store)
    dead = [key for key, stamp in before.items() if now.get(key) == stamp]
    if dead:
        _write(store, {key: stamp for key, stamp in now.items() if key not in dead})
    return dead


def _read(store: Path) -> dict[str, str]:
    try:
        text = store.read_text(encoding="utf-8")
    except OSError:
        return {}
    entries: dict[str, str] = {}
    for line in text.splitlines():
        key, sep, stamp = line.partition("=")
        if sep and key:
            entries[key] = stamp
    return entries


def _write(store: Path, entries: dict[str, str]) -> None:
    scratch = store.with_name(store.name + ".retire")
    scratch.write_text("\n".join(f"{key}={stamp}" for key, stamp in entries.items()), encoding="utf-8")
    os.replace(scratch, store)
