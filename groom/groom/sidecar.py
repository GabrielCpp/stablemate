"""``groom-sidecar`` — runs inside each agent container, watching its own
``/workspace`` and ``/runs`` mounts with real inotify and holding one
persistent WebSocket open to the host's ``groom`` process.

The socket is the container's live session: the sidecar dials groom (it is the
client, so no inbound reachability into the container is needed), advertises its
identity + full current state on connect, streams ``progress``/``blocked``
deltas from inotify, and answers ``getTree``/``getFile``/``getDiff`` RPCs from
local disk — the data plane for groom's Files/Diff panels. A reconnect-with-
backoff loop (built into ``websockets.connect``) means groom being down is never
fatal; the sidecar just keeps trying and re-advertises on reconnect.

The session is **non-authoritative and its state ephemeral**: everything
re-syncs on (re)connect, so a dropped socket, a groom restart, or a container
recreate is cheap and safe. The sidecar has zero say in the workflow's own exit
code or behaviour — it only ever observes and serves reads.

Runs as its own OS process (``groom-sidecar`` in the container entrypoint's
supervising loop, ahead of workhorse's own run command), not embedded in
workhorse's event loop. A ``reload`` command over the socket makes it exit with
:data:`RELOAD_EXIT_CODE` so the entrypoint can recopy edited source and relaunch
(see ``docs/features/groom/sidecar-live-sessions.md``).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from inotify_simple import INotify, flags
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from groom.gates import AWAITING, extract_question, status_of

WORKSPACE_DIR = Path(os.environ.get("GROOM_WORKSPACE_DIR", "/workspace"))
RUNS_DIR = Path(os.environ.get("GROOM_RUNS_DIR", "/runs"))
GROOM_HOST = os.environ.get("GROOM_HOST", "host.docker.internal")
GROOM_PORT = os.environ.get("GROOM_PORT", "8787")
PUSH_TIMEOUT = float(os.environ.get("GROOM_PUSH_TIMEOUT", "1.0"))

# Exit code reserved for an intentional reload request (outside the normal
# 0/1/2, 126/127, 128+signal ranges): the entrypoint's supervising loop reads
# it as "recopy the edited source and relaunch me", anything else as "stop".
RELOAD_EXIT_CODE = 3

_WATCH_FLAGS = flags.MODIFY | flags.CLOSE_WRITE | flags.CREATE | flags.MOVED_TO
_SKIP_DIR_NAMES = {".git", "node_modules", "__pycache__", ".venv"}


def _identity() -> dict:
    return {
        "container_id": socket.gethostname()[:12],
        "name": os.environ.get("REPO_NAME", socket.gethostname()),
        "repo_name": os.environ.get("REPO_NAME", ""),
        "repo_branch": os.environ.get("REPO_BRANCH", ""),
    }


# --------------------------------------------------------------------------- #
# Residual best-effort HTTP push (fire-and-forget)
#
# The persistent socket is the primary channel; these remain for the one-shot
# ``exited`` notice the entrypoint fires after workhorse returns (the socket is
# torn down with the container by then) and for the ``await_operator.py``
# backstop that POSTs ``/push/blocked`` directly. Discipline is unchanged: short
# timeout, silent on failure, never blocks or changes the workflow's exit code.
# --------------------------------------------------------------------------- #
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
    ``groom-sidecar --exit-code``) — not from the session, which by then is
    being torn down with the container.
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


def _terminal() -> str:
    """The latest run's terminal state (non-empty ⇒ the workflow FINISHED),
    read from ``<latest>/run.json`` — the pull-side complement to the inotify
    loop, which only ever reports the current node.
    """
    run_dir = _latest_run_dir()
    if run_dir is None:
        return ""
    run_json = run_dir / "run.json"
    if not run_json.is_file():
        return ""
    try:
        return json.loads(run_json.read_text()).get("terminal") or ""
    except (OSError, json.JSONDecodeError):
        return ""


# STATUS: is the first line of a gate context file, so a small head read is
# enough to classify a file without slurping large source files whole.
_GATE_SCAN_HEAD = 512


def scan_gates() -> list[dict]:
    """A one-shot sweep of ``/workspace`` for every file whose STATUS line reads
    AWAITING_OPERATOR — the pull-side equivalent of what ``_classify_event``
    emits reactively, so a fresh ``hello`` advertises gates that were already
    open before any inotify event fired. Same directory skips as the watcher.
    """
    gates: list[dict] = []
    if not WORKSPACE_DIR.is_dir():
        return gates
    for dirpath, dirnames, filenames in os.walk(WORKSPACE_DIR):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES]
        for fname in filenames:
            fpath = Path(dirpath) / fname
            try:
                with fpath.open("r", errors="replace") as fh:
                    head = fh.read(_GATE_SCAN_HEAD)
            except OSError:
                continue
            if status_of(head) != AWAITING:
                continue
            try:
                content = fpath.read_text(errors="replace")
            except OSError:
                continue
            try:
                rel_path = str(fpath.relative_to(WORKSPACE_DIR))
            except ValueError:
                rel_path = str(fpath)
            gates.append({"file_path": rel_path, "question": extract_question(content)})
    return gates


def snapshot() -> dict:
    """The container's full current state: current graph node, terminal state,
    and every open gate. Pure file reads — no inotify, no network — so it is
    safe both as the ``hello`` payload and as the one-shot ``--query`` a legacy
    host uses over ``docker exec``.
    """
    return {
        "current_node": _current_node(),
        "terminal": _terminal(),
        "gates": scan_gates(),
    }


# --------------------------------------------------------------------------- #
# inotify → event classification (shared by the socket session and the residual
# HTTP path). Pure: given an already-received event it decides which frame, if
# any, to emit, without any transport.
# --------------------------------------------------------------------------- #
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


def _classify_event(event, wd_to_path: dict[int, str]) -> dict | None:
    """Translate one non-directory inotify event into the frame to send, or
    ``None`` when it is uninteresting. A ``/runs`` write means graph progress; a
    ``/workspace`` write whose STATUS flipped to AWAITING_OPERATOR is a new
    gate. Directory events (new subtree to watch) are handled by the caller,
    which owns the ``inotify`` handle.
    """
    parent = wd_to_path.get(event.wd)
    if parent is None:
        return None
    full_path = Path(parent) / event.name
    if bool(event.mask & flags.ISDIR):
        return None

    try:
        under_runs = full_path.is_relative_to(RUNS_DIR)
    except ValueError:
        under_runs = False
    if under_runs:
        return {"type": "progress", "current_node": _current_node()}

    try:
        content = full_path.read_text()
    except OSError:
        return None
    if status_of(content) != AWAITING:
        return None
    try:
        rel_path = str(full_path.relative_to(WORKSPACE_DIR))
    except ValueError:
        rel_path = str(full_path)
    return {"type": "blocked", "file_path": rel_path, "question": extract_question(content)}


def _handle_event(inotify: INotify, event, wd_to_path: dict[int, str]) -> None:
    """Residual HTTP path: classify one event and fire the matching
    fire-and-forget push. The socket session (:func:`_run_session`) uses
    :func:`_classify_event` directly instead; this is retained as the
    best-effort push shape and for its focused unit tests.
    """
    parent = wd_to_path.get(event.wd)
    if parent is None:
        return
    if bool(event.mask & flags.ISDIR):
        if event.mask & (flags.CREATE | flags.MOVED_TO):
            _add_watches(inotify, Path(parent) / event.name, wd_to_path)
        return
    frame = _classify_event(event, wd_to_path)
    if frame is None:
        return
    if frame["type"] == "progress":
        push_progress(frame["current_node"])
    elif frame["type"] == "blocked":
        push_blocked(frame["file_path"], frame["question"])


# --------------------------------------------------------------------------- #
# Data-plane RPC handlers — the reads groom's Files/Diff panels ask for, served
# from this container's own local disk. The traversal guard travels with the
# read (this is an unauthenticated file server for its own volume).
# --------------------------------------------------------------------------- #
def _safe_relpath(path: str) -> str:
    if not path or path.startswith("/") or path.startswith("\\"):
        raise ValueError(f"unsafe path: {path!r}")
    parts = path.replace("\\", "/").split("/")
    if any(part in ("", "..") for part in parts):
        raise ValueError(f"unsafe path: {path!r}")
    return "/".join(parts)


def _repo_base(repo: str) -> Path:
    return WORKSPACE_DIR / repo if repo else WORKSPACE_DIR


def _find_repo_dirs() -> list[str]:
    """Volume-relative paths of every git checkout within two levels of the
    workspace root — mirrors ``docker_io.list_repo_dirs`` so the socket and the
    fallback agree. ``""`` denotes the workspace root itself being the repo.
    """
    if not WORKSPACE_DIR.is_dir():
        return []
    repos: list[str] = []
    if (WORKSPACE_DIR / ".git").is_dir():
        repos.append("")
    for child in WORKSPACE_DIR.iterdir():
        if child.is_dir() and child.name != ".git" and (child / ".git").is_dir():
            repos.append(child.name)
    return sorted(repos)


def _list_tree(repo: str) -> list[str]:
    """Repo-relative paths of every file in one checkout, heavy vendor/VCS dirs
    pruned (same set as the watcher). Sorted for a stable tree order."""
    base = _repo_base(repo)
    if not base.is_dir():
        return []
    paths: list[str] = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIR_NAMES]
        for fname in filenames:
            full = Path(dirpath) / fname
            try:
                paths.append(str(full.relative_to(base)))
            except ValueError:
                continue
    return sorted(paths)


def _git_diff(repo: str) -> str:
    """Unified working-tree-vs-HEAD diff for one checkout, run against local
    disk. ``""`` falls back to the first repo found. "" on any failure — the
    diff panel is a nice-to-have, never workflow-critical.
    """
    if not repo:
        repos = _find_repo_dirs()
        if not repos:
            return ""
        repo = repos[0]
    try:
        proc = subprocess.run(
            ["git", "-c", "safe.directory=*", "-C", str(_repo_base(repo)), "diff", "HEAD"],
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return proc.stdout if proc.returncode == 0 else ""


def _rpc_get_tree(params: dict) -> dict:
    return {"paths": _list_tree(str(params.get("repo", "")))}


def _rpc_get_file(params: dict) -> dict:
    repo = str(params.get("repo", ""))
    path = str(params.get("path", ""))
    rel = f"{repo}/{path}".lstrip("/") if repo else path
    if not rel:
        return {"content": ""}
    safe = _safe_relpath(rel)  # raises ValueError on traversal → error result
    try:
        content = (WORKSPACE_DIR / safe).read_text(errors="replace")
    except OSError:
        content = ""
    return {"content": content}


def _rpc_get_diff(params: dict) -> dict:
    return {"diff": _git_diff(str(params.get("repo", "")))}


_RPC_METHODS = {
    "getTree": _rpc_get_tree,
    "getFile": _rpc_get_file,
    "getDiff": _rpc_get_diff,
}


# --------------------------------------------------------------------------- #
# The persistent socket session
# --------------------------------------------------------------------------- #
class ReloadRequested(Exception):
    """Raised inside a session when groom sends ``reload``; unwinds the session
    so :func:`_serve` returns :data:`RELOAD_EXIT_CODE`."""


def _hello_frame() -> dict:
    """Full-state advertise sent on every (re)connect. groom folds this into its
    fleet without a ``docker inspect`` — the socket owns correctness for a
    connected container, and re-sending it on reconnect self-heals a groom
    restart.
    """
    return {"type": "hello", "identity": _identity(), "snapshot": snapshot()}


async def _handle_rpc(ws, msg: dict) -> None:
    corr_id = msg.get("id")
    method = str(msg.get("method", ""))
    params = msg.get("params") or {}
    handler = _RPC_METHODS.get(method)
    if handler is None:
        await ws.send(json.dumps({"type": "rpc_result", "id": corr_id, "ok": False, "error": f"unknown method {method!r}"}))
        return
    try:
        data = await asyncio.to_thread(handler, params)
    except Exception as exc:  # noqa: BLE001 - any read failure becomes an error result, never crashes the session
        await ws.send(json.dumps({"type": "rpc_result", "id": corr_id, "ok": False, "error": str(exc)}))
        return
    await ws.send(json.dumps({"type": "rpc_result", "id": corr_id, "ok": True, "data": data}))


async def _sender_loop(ws, outbox: asyncio.Queue) -> None:
    while True:
        frame = await outbox.get()
        await ws.send(json.dumps(frame))


async def _run_session(ws) -> None:
    """One connected session: advertise, then serve inotify deltas (outbound via
    a queue fed by an fd reader) and RPC/reload (inbound) until the socket drops
    or a reload is requested.
    """
    await ws.send(json.dumps(_hello_frame()))

    loop = asyncio.get_running_loop()
    inotify = INotify()
    wd_to_path: dict[int, str] = {}
    _add_watches(inotify, WORKSPACE_DIR, wd_to_path)
    _add_watches(inotify, RUNS_DIR, wd_to_path)
    outbox: asyncio.Queue = asyncio.Queue()

    def _on_readable() -> None:
        # Non-blocking drain from the event loop's fd reader — never blocks the
        # loop, and new subtrees get their own watch as they appear.
        for event in inotify.read(timeout=0):
            if bool(event.mask & flags.ISDIR):
                if event.mask & (flags.CREATE | flags.MOVED_TO):
                    parent = wd_to_path.get(event.wd)
                    if parent:
                        _add_watches(inotify, Path(parent) / event.name, wd_to_path)
                continue
            frame = _classify_event(event, wd_to_path)
            if frame is not None:
                outbox.put_nowait(frame)

    loop.add_reader(inotify.fileno(), _on_readable)
    sender = asyncio.create_task(_sender_loop(ws, outbox))
    try:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError, ValueError):
                continue
            mtype = msg.get("type")
            if mtype == "rpc":
                await _handle_rpc(ws, msg)
            elif mtype == "reload":
                raise ReloadRequested
    finally:
        loop.remove_reader(inotify.fileno())
        sender.cancel()
        with contextlib.suppress(asyncio.CancelledError, ConnectionClosed):
            await sender
        inotify.close()


async def _serve() -> int:
    """Dial groom and hold a session open, reconnecting with backoff (built into
    ``connect``) whenever the socket drops. Returns only on a reload request
    (with :data:`RELOAD_EXIT_CODE`) — otherwise it retries forever, so groom
    being down is never fatal.
    """
    uri = f"ws://{GROOM_HOST}:{GROOM_PORT}/sidecar"
    async for ws in connect(uri):
        try:
            await _run_session(ws)
        except ReloadRequested:
            with contextlib.suppress(Exception):
                await ws.close()
            return RELOAD_EXIT_CODE
        except ConnectionClosed:
            continue  # reconnect and re-advertise
    return 0


def run() -> None:
    exit_code = asyncio.run(_serve())
    if exit_code:
        raise SystemExit(exit_code)
