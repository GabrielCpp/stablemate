"""A run's `inbox.jsonl`, read and appended on a native host path or inside a docker runs volume."""

from __future__ import annotations

from pathlib import Path

from groom import docker_io
from groom.models import WorkflowContainer
from workhorse import inbox

_INBOX_FILE = "inbox.jsonl"


def _docker_inbox_rel_path(runs_volume: str) -> str | None:
    """The volume-relative path to the latest run's inbox file, or ``None`` when the volume has no run directory yet — mirrors how ``discovery._current_run_state`` finds the live run inside a runs volume."""
    dirs = docker_io.list_run_dirs(runs_volume)
    if not dirs:
        return None
    return f"{dirs[-1]}/{_INBOX_FILE}"


def messages(wf: WorkflowContainer) -> list[inbox.Message]:
    """Every message in this run's inbox, oldest first — a plain read over :mod:`workhorse.inbox` for a native run, whose ``runs_volume`` is a real host path."""
    if not wf.runs_volume:
        return []
    if wf.native:
        return inbox.all_messages(Path(wf.runs_volume) / _INBOX_FILE)
    rel_path = _docker_inbox_rel_path(wf.runs_volume)
    if rel_path is None:
        return []
    raw = docker_io.read_file(wf.runs_volume, rel_path)
    if not raw:
        return []
    return [inbox.Message.model_validate_json(line) for line in raw.splitlines() if line.strip()]


def append(wf: WorkflowContainer, *, message_id: str, body: str, at: str) -> inbox.Message | None:
    """Append one operator message and return it, or ``None`` when the run has no directory yet to append into (a docker run whose first run dir hasn't been created)."""
    if wf.native:
        return inbox.append(Path(wf.runs_volume) / _INBOX_FILE, id=message_id, body=body, at=at)
    rel_path = _docker_inbox_rel_path(wf.runs_volume)
    if rel_path is None:
        return None
    message = inbox.Message.model_validate({"id": message_id, "body": body, "at": at})
    existing = docker_io.read_file(wf.runs_volume, rel_path) or ""
    ok = docker_io.write_file(wf.runs_volume, rel_path, existing + message.model_dump_json() + "\n")
    return message if ok else None
