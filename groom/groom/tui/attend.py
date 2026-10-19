from __future__ import annotations

import time
from datetime import datetime

from rich.text import Text

from groom.tui.clean import clean
from groom.tui.link import Frame

LOADING_TEXT = "Loading attendances…"
EMPTY_TEXT = "No attendance yet. groom has not sent an agent at a parked or dead run."
NO_SELECTION_TEXT = "Select an attendance to read what the agent did."
NO_TRANSCRIPT_TEXT = "No transcript on disk for this session yet. It is copied when the agent exits."
UNKNOWN_WORKFLOW = "(unknown workflow)"
STATUS_STYLE = {"running": "bold green", "completed": "dim"}


def session_of(row: Frame) -> str:
    sessions = row.get("session_ids") or []
    return str(sessions[-1]) if sessions else ""


def workflow_of(row: Frame) -> str:
    return clean(row.get("workflow")) or UNKNOWN_WORKFLOW


def when(epoch: object) -> str:
    if not isinstance(epoch, int | float) or not epoch:
        return ""
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S")


def elapsed(row: Frame, now: float | None = None) -> str:
    end = row.get("ended_at") or (time.time() if now is None else now)
    secs = max(0, round(end - (row.get("started_at") or 0)))
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60}s"
    return f"{secs // 3600}h {secs % 3600 // 60}m"


def outcome(row: Frame) -> str:
    if row.get("status") == "running":
        return "running"
    text = "completed"
    if row.get("exit_code") is not None:
        text += f" · exit {clean(row['exit_code'])}"
    if row.get("released_state"):
        text += f" · {clean(row['released_state'])}"
    return text


def row_text(row: Frame, now: float | None = None) -> Text:
    text = Text(no_wrap=True, overflow="ellipsis")
    text.append(outcome(row), style=STATUS_STYLE.get(str(row.get("status")), "dim"))
    text.append("  " + workflow_of(row), style="bold")
    meta = [clean(row.get("reason") or row.get("kind")), when(row.get("started_at")), elapsed(row, now)]
    if row.get("node"):
        meta.append(f"node {clean(row['node'])}")
    text.append("\n" + " · ".join(part for part in meta if part), style="dim")
    return text


def head_text(record: Frame) -> Text:
    text = Text()
    text.append(clean(record.get("workflow")), style="bold")
    text.append("  " + clean(record.get("run_id")), style="dim")
    status = clean(record.get("status"))
    text.append("  " + status, style=STATUS_STYLE.get(status, ""))
    for name in ("reason", "run_dir"):
        if record.get(name):
            text.append("\n" + clean(record[name]), style="dim" if name == "run_dir" else "")
    return text


def attempts_text(attempts: list[str]) -> Text:
    if len(attempts) < 2:
        return Text()
    return Text("earlier sessions: " + " ".join(clean(item) for item in attempts[:-1]), style="dim")


def attendant_line(entry: Frame | None) -> Text:
    if not entry:
        return Text()
    label = "an attendant is on this run" if entry.get("status") == "running" else "last attendant"
    reason = clean(entry.get("reason"))
    return Text(label + (f" · {reason}" if reason else "") + "  (A)", style="dim")
