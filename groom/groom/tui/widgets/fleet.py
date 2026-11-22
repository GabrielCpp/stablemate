from __future__ import annotations

import time

from rich.text import Text

from groom.tui import store as client
from groom.tui.clean import clean
from groom.tui.connection import Connection
from groom.tui.link import Frame

PHASE_GLYPH = {"live": "●", "stale": "◐", "reconnecting": "◌", "offline": "○"}
PHASE_STYLE = {"live": "green", "stale": "yellow", "reconnecting": "yellow", "offline": "red"}
SCANNING_TEXT = "Discovering containers…"
NO_MATCH_TEXT = "No run matches “{query}”."
EMPTY_TEXT = "No workhorse runs — nothing is running."


def status_text(connection: Connection, store: client.Store) -> Text:
    text = Text(no_wrap=True, overflow="ellipsis")
    text.append(f"{PHASE_GLYPH[connection.phase]} {connection.phase}", style=f"bold {PHASE_STYLE[connection.phase]}")
    counts = store.status.get("counts") or {}
    total = store.status.get("workers", len(store.runs))
    text.append(f"  {total} runs")
    for name in ("blocked", "running", "idle", "finished"):
        if counts.get(name):
            text.append(f" · {counts[name]} {name}")
    if not store.runs:
        text.append("  " + (SCANNING_TEXT if store.scanning else EMPTY_TEXT))
    elif store.query.strip():
        shown = len(client.filter_runs(store.runs, store.query))
        text.append(f"  filter: {clean(store.query.strip())}  {shown} of {len(store.runs)}")
    return text


def span_label(since: float, now: float | None = None) -> str:
    secs = max(0, round((time.time() if now is None else now) - since))
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m"
    return f"{secs // 3600}h"


def live_label(row: Frame, now: float | None = None) -> str:
    seen = float(row.get("last_seen_ts") or 0)
    if row.get("live") == "dead" and not row.get("ended") and seen > 0:
        return "silent " + span_label(seen, now)
    return clean(row.get("live_label"))


def row_text(row: Frame, now: float | None = None) -> Text:
    text = Text(no_wrap=True, overflow="ellipsis")
    if int(row.get("gate_count") or 0) > 0:
        text.append("▲ gate ", style="bold yellow")
    else:
        text.append("       ")
    text.append(f"{live_label(row, now) or 'unknown':<12}")
    text.append(clean(row.get("name")), style="bold")
    doing = clean(row.get("doing") or row.get("node") or "")
    if doing:
        text.append("  " + doing, style="dim")
    return text
