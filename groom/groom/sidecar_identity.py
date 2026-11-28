"""Who a sidecar's run is: the container id rule, the run record's ids, the hello sent again on a change, and the wait for a mount that is not there yet."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import socket
from collections.abc import Callable
from pathlib import Path


def container_id(dockerenv: Path) -> str:
    """The container this sidecar runs in: named by ``GROOM_CONTAINER_ID``, else the hostname inside Docker, else nothing."""
    named = os.environ.get("GROOM_CONTAINER_ID", "")
    if named:
        return named
    return socket.gethostname()[:12] if dockerenv.exists() else ""


def repo_name(start: dict) -> str:
    for key in ("root", "path"):
        value = start.get(key)
        if isinstance(value, str) and value:
            return Path(value).name
    return ""


def latest_run_dir(runs_dir: Path) -> Path | None:
    if not runs_dir.is_dir():
        return None
    run_dirs = sorted(p for p in runs_dir.iterdir() if p.is_dir())
    return run_dirs[-1] if run_dirs else None


def run_record(runs_dir: Path) -> dict:
    """The latest run's ``run.json`` as a dict, or an empty one while there is none or it cannot be read."""
    run_dir = latest_run_dir(runs_dir)
    if run_dir is None:
        return {}
    try:
        record = json.loads((run_dir / "run.json").read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return record if isinstance(record, dict) else {}


def identity(runs_dir: Path, dockerenv: Path) -> dict:
    """Who this run is, for the dashboard row and for joining it to telemetry: the latest run's record first, the environment while the record lacks the field."""
    record = run_record(runs_dir)
    start = record.get("repo_start")
    start = start if isinstance(start, dict) else {}
    repo = repo_name(start) or os.environ.get("REPO_NAME", "")
    return {
        "container_id": container_id(dockerenv),
        "name": repo or socket.gethostname(),
        "repo_name": repo,
        "repo_branch": str(start.get("branch") or "") or os.environ.get("REPO_BRANCH", ""),
        "run_id": str(record.get("run_id") or "") or os.environ.get("AGENT_RUN_ID", ""),
        "workflow": str(record.get("workflow") or "") or os.environ.get("WORKFLOW", ""),
    }


class Announced:
    """The identity the groom host last heard, so a change in the run record can say hello again."""

    def __init__(self, heard: dict, read: Callable[[], dict], frame: Callable[[dict], dict]) -> None:
        self._heard = heard
        self._read = read
        self._frame = frame

    def refresh(self, *, force: bool = False) -> dict | None:
        current = self._read()
        if current == self._heard and not force:
            return None
        self._heard = current
        return self._frame(current)


async def follow_mounts(mounts: Callable[[], list[Path]], roots: list[Path], stop: asyncio.Event, ending: asyncio.Event, poll_s: float) -> None:
    """Set ``ending`` when the mounts that exist differ from ``roots``, or when ``stop`` is set."""
    while not stop.is_set() and mounts() == roots:
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(stop.wait(), poll_s)
    ending.set()
