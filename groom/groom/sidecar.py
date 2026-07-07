"""``groom-sidecar`` — runs inside each agent container, watching its own
``/workspace`` and ``/runs`` mounts with real inotify and pushing
fire-and-forget HTTP updates to the host's ``groom`` process.

Every push is wrapped in a broad ``except`` with a short timeout and is
completely silent on failure: a container with no ``groom`` listening (or no
network path to it) behaves exactly as it does today. This module has zero
say in the workflow's own exit code or behavior — it only ever observes.

Runs as its own OS process (``groom-sidecar &`` in the container entrypoint,
ahead of workhorse's own run command), not embedded in workhorse's event
loop.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from pathlib import Path

from inotify_simple import INotify, flags

from .gates import AWAITING, extract_question, status_of

WORKSPACE_DIR = Path(os.environ.get("GROOM_WORKSPACE_DIR", "/workspace"))
RUNS_DIR = Path(os.environ.get("GROOM_RUNS_DIR", "/runs"))
GROOM_HOST = os.environ.get("GROOM_HOST", "host.docker.internal")
GROOM_PORT = os.environ.get("GROOM_PORT", "8787")
PUSH_TIMEOUT = float(os.environ.get("GROOM_PUSH_TIMEOUT", "1.0"))

_WATCH_FLAGS = flags.MODIFY | flags.CLOSE_WRITE | flags.CREATE | flags.MOVED_TO
_SKIP_DIR_NAMES = {".git", "node_modules", "__pycache__", ".venv"}


def _identity() -> dict:
    return {
        "container_id": socket.gethostname()[:12],
        "name": os.environ.get("REPO_NAME", socket.gethostname()),
        "repo_name": os.environ.get("REPO_NAME", ""),
        "repo_branch": os.environ.get("REPO_BRANCH", ""),
    }


def _push(path: str, payload: dict) -> None:
    body = json.dumps({**_identity(), **payload}).encode("utf-8")
    url = f"http://{GROOM_HOST}:{GROOM_PORT}{path}"
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(request, timeout=PUSH_TIMEOUT).close()
    except Exception:
        pass


def push_progress(current_node: str = "") -> None:
    _push("/push/progress", {"current_node": current_node})


def push_blocked(file_path: str, question: str) -> None:
    _push("/push/blocked", {"file_path": file_path, "question": question})


def push_exited(exit_code: int) -> None:
    """Fire-and-forget notice that the workflow process has ended. Invoked once
    from the container entrypoint after ``workhorse`` returns (see cli
    ``groom-sidecar --exit-code``) — not from the inotify loop, which by then
    is being torn down with the container.
    """
    _push("/push/exited", {"exit_code": exit_code})


def _latest_run_dir() -> Path | None:
    if not RUNS_DIR.is_dir():
        return None
    run_dirs = sorted(p for p in RUNS_DIR.iterdir() if p.is_dir())
    return run_dirs[-1] if run_dirs else None


def _current_node() -> str:
    run_dir = _latest_run_dir()
    if run_dir is None:
        return ""
    checkpoint = run_dir / "checkpoint.json"
    if not checkpoint.is_file():
        return ""
    try:
        return json.loads(checkpoint.read_text()).get("current_id", "")
    except (OSError, json.JSONDecodeError):
        return ""


def _add_watches(inotify: INotify, root: Path, wd_to_path: dict[int, str]) -> None:
    if not root.is_dir():
        return
    for dirpath, dirnames, _filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES]
        try:
            wd = inotify.add_watch(dirpath, _WATCH_FLAGS)
        except OSError:
            continue
        wd_to_path[wd] = dirpath


def _handle_event(inotify: INotify, event, wd_to_path: dict[int, str]) -> None:
    parent = wd_to_path.get(event.wd)
    if parent is None:
        return
    full_path = Path(parent) / event.name
    is_dir_event = bool(event.mask & flags.ISDIR)

    if is_dir_event:
        if event.mask & (flags.CREATE | flags.MOVED_TO):
            _add_watches(inotify, full_path, wd_to_path)
        return

    try:
        under_runs = full_path.is_relative_to(RUNS_DIR)
    except ValueError:
        under_runs = False

    if under_runs:
        push_progress(_current_node())
        return

    try:
        content = full_path.read_text()
    except OSError:
        return

    if status_of(content) == AWAITING:
        try:
            rel_path = str(full_path.relative_to(WORKSPACE_DIR))
        except ValueError:
            rel_path = str(full_path)
        push_blocked(rel_path, extract_question(content))


def run() -> None:
    inotify = INotify()
    wd_to_path: dict[int, str] = {}
    _add_watches(inotify, WORKSPACE_DIR, wd_to_path)
    _add_watches(inotify, RUNS_DIR, wd_to_path)

    while True:
        for event in inotify.read(timeout=1000):
            _handle_event(inotify, event, wd_to_path)
