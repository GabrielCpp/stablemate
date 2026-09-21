"""``groom-sidecar`` — runs inside each agent container, watching its own ``/workspace`` and ``/runs`` mounts and holding one persistent WebSocket open to the host's ``groom`` process."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import os
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from watchfiles import Change, DefaultFilter, awatch
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from workhorse import control

from groom.checkpoints import parse_position
from groom.gates import AWAITING, extract_question, status_of

WORKSPACE_DIR = Path(os.environ.get("GROOM_WORKSPACE_DIR", "/workspace"))
RUNS_DIR = Path(os.environ.get("GROOM_RUNS_DIR", "/runs"))
GROOM_HOST = os.environ.get("GROOM_HOST", "host.docker.internal")
GROOM_PORT = os.environ.get("GROOM_PORT", "8787")
PUSH_TIMEOUT = float(os.environ.get("GROOM_PUSH_TIMEOUT", "1.0"))

RELOAD_EXIT_CODE = 3

_SKIP_DIR_NAMES = {".git", "node_modules", "__pycache__", ".venv"}
_WATCH_FILTER = DefaultFilter(ignore_dirs=sorted(_SKIP_DIR_NAMES))


def _identity() -> dict:
    """Who this container is, for the dashboard row and for joining it to telemetry."""
    return {
        "container_id": socket.gethostname()[:12],
        "name": os.environ.get("REPO_NAME", socket.gethostname()),
        "repo_name": os.environ.get("REPO_NAME", ""),
        "repo_branch": os.environ.get("REPO_BRANCH", ""),
        "run_id": os.environ.get("AGENT_RUN_ID", ""),
        "workflow": os.environ.get("WORKFLOW", ""),
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
    """Fire-and-forget notice that the workflow process has ended."""
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
        return parse_position(checkpoint.read_text()).current_node
    except OSError:
        return ""


def _terminal() -> str:
    """The latest run's terminal state (non-empty ⇒ the workflow FINISHED), read from ``<latest>/run.json`` — the pull-side complement to the watch loop, which only ever reports the current node."""
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


_GATE_SCAN_HEAD = 512


def scan_gates() -> list[dict]:
    """A one-shot sweep of ``/workspace`` for every file whose STATUS line reads AWAITING_OPERATOR — the pull-side equivalent of what ``_classify_event`` emits reactively, so a fresh ``hello`` advertises gates that were already open before any change event fired."""
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
    """The container's full current state: current graph node, terminal state, and every open gate."""
    return {
        "current_node": _current_node(),
        "terminal": _terminal(),
        "gates": scan_gates(),
    }


def _watch_roots() -> list[Path]:
    """The mounts to hand ``awatch``, minus any that is not there."""
    return [root for root in (WORKSPACE_DIR, RUNS_DIR) if root.is_dir()]


def _under_mount(path: Path, mount: Path) -> Path | None:
    """``path`` relative to ``mount``, or ``None`` when it is not under it."""
    try:
        return path.relative_to(mount)
    except ValueError:
        pass
    try:
        return Path(os.path.realpath(path)).relative_to(os.path.realpath(mount))
    except ValueError:
        return None


def _classify_event(path: Path) -> dict | None:
    """Translate one changed path into the frame to send, or ``None`` when it is uninteresting."""
    if _under_mount(path, RUNS_DIR) is not None:
        return {"type": "progress", "current_node": _current_node()}

    try:
        content = path.read_text()
    except OSError:
        return None
    if status_of(content) != AWAITING:
        return None
    relative = _under_mount(path, WORKSPACE_DIR)
    rel_path = str(relative) if relative is not None else str(path)
    return {"type": "blocked", "file_path": rel_path, "question": extract_question(content)}


def _turn_announce(path: Path) -> dict | None:
    """A ``turn`` frame when a changed path is part of a run's turn-record surface."""
    relative = _under_mount(path, RUNS_DIR)
    if relative is None:
        return None
    parts = relative.parts
    if len(parts) < 2 or parts[1] not in TURN_SURFACE:
        return None
    return {"type": "turn", "run": parts[0], **_identity()}


def _handle_event(path: Path) -> None:
    """Residual HTTP path: classify one changed path and fire the matching fire-and-forget push."""
    frame = _classify_event(path)
    if frame is None:
        return
    if frame["type"] == "progress":
        push_progress(frame["current_node"])
    elif frame["type"] == "blocked":
        push_blocked(frame["file_path"], frame["question"])


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
    """Volume-relative paths of every git checkout within two levels of the workspace root — mirrors ``docker_io.list_repo_dirs`` so the socket and the fallback agree."""
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
    """Repo-relative paths of every file in one checkout, heavy vendor/VCS dirs pruned (same set as the watcher)."""
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
    """Unified working-tree-vs-HEAD diff for one checkout, run against local disk."""
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
    safe = _safe_relpath(rel)
    try:
        content = (WORKSPACE_DIR / safe).read_text(errors="replace")
    except OSError:
        content = ""
    return {"content": content}


def _rpc_get_diff(params: dict) -> dict:
    return {"diff": _git_diff(str(params.get("repo", "")))}



TURN_SURFACE = ("sessions.jsonl", "transcripts", "turns")

TURN_CHUNK_BYTES = 512 * 1024


def _run_base(run: str) -> Path:
    """The run dir a turn-record RPC is talking about — named, or the latest."""
    if run:
        return RUNS_DIR / _safe_relpath(run)
    latest = _latest_run_dir()
    if latest is None:
        raise ValueError("no run directory")
    return latest


def _within_runs(path: Path) -> Path:
    """``path``, having confirmed it really resolves under ``RUNS_DIR``."""
    root = Path(os.path.realpath(RUNS_DIR))
    resolved = Path(os.path.realpath(path))
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"outside the runs volume: {path}")
    return resolved


def _turn_files(base: Path) -> list[dict]:
    """Every file of the turn-record surface in one run dir, with its size."""
    files: list[dict] = []
    for name in TURN_SURFACE:
        target = base / name
        if target.is_file():
            entries = [(name, target)]
        elif target.is_dir():
            entries = [
                (f"{name}/{p.relative_to(target).as_posix()}", p)
                for p in sorted(target.rglob("*"))
                if p.is_file()
            ]
        else:
            continue
        for rel, path in entries:
            try:
                files.append({"path": rel, "size": path.stat().st_size})
            except OSError:
                continue
    return files


def _rpc_list_turns(params: dict) -> dict:
    base = _run_base(str(params.get("run", "")))
    return {"run": base.name, "files": _turn_files(base)}


def _rpc_read_turn_file(params: dict) -> dict:
    """One slice of one turn-record file, base64'd."""
    base = _run_base(str(params.get("run", "")))
    rel = _safe_relpath(str(params.get("path", "")))
    if rel.split("/")[0] not in TURN_SURFACE:
        raise ValueError(f"not a turn record: {rel}")
    offset = max(0, int(params.get("offset", 0)))
    length = min(max(0, int(params.get("length", TURN_CHUNK_BYTES))), TURN_CHUNK_BYTES)
    full = _within_runs(base / rel)
    size = full.stat().st_size
    with full.open("rb") as fh:
        fh.seek(offset)
        data = fh.read(length)
    return {
        "data": base64.b64encode(data).decode("ascii"),
        "offset": offset,
        "size": size,
        "eof": offset + len(data) >= size,
    }


CONTROL_TIMEOUT = 4.0


def _relay_to_control(run: str, request: control.Request) -> dict:
    """One control-socket exchange with the named (or latest) run."""
    base = _run_base(run)
    try:
        return dict(control.send(str(base), request, timeout=CONTROL_TIMEOUT))
    except FileNotFoundError:
        return {"ok": False, "error": "no listener"}


def _rpc_get_questions(params: dict) -> dict:
    return _relay_to_control(
        str(params.get("run", "")), control.Request(action=control.QUESTIONS)
    )


def _rpc_answer_gate(params: dict) -> dict:
    request = control.Request(
        action=control.ANSWER,
        path=str(params.get("path", "")),
        body=str(params.get("body", "")),
    )
    return _relay_to_control(str(params.get("run", "")), request)


_RPC_METHODS = {
    "getTree": _rpc_get_tree,
    "getFile": _rpc_get_file,
    "getDiff": _rpc_get_diff,
    "listTurns": _rpc_list_turns,
    "readTurnFile": _rpc_read_turn_file,
    "getQuestions": _rpc_get_questions,
    "answerGate": _rpc_answer_gate,
}


class ReloadRequested(Exception):
    """Raised inside a session when groom sends ``reload``; unwinds the session so :func:`_serve` returns :data:`RELOAD_EXIT_CODE`."""


def _hello_frame() -> dict:
    """Full-state advertise sent on every (re)connect."""
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


async def _watch_loop(outbox: asyncio.Queue, stop: asyncio.Event) -> None:
    """Feed the outbox from the filesystem watch until ``stop`` is set."""
    roots = _watch_roots()
    if not roots:
        return
    async for changes in awatch(*roots, watch_filter=_WATCH_FILTER, stop_event=stop):
        for change, raw_path in changes:
            if change is Change.deleted:
                continue
            changed = Path(raw_path)
            for frame in (_classify_event(changed), _turn_announce(changed)):
                if frame is not None:
                    outbox.put_nowait(frame)


async def _run_session(ws) -> None:
    """One connected session: advertise, then serve filesystem deltas (outbound via a queue fed by the watch task) and RPC/reload (inbound) until the socket drops or a reload is requested."""
    await ws.send(json.dumps(_hello_frame()))

    outbox: asyncio.Queue = asyncio.Queue()
    stop = asyncio.Event()
    watcher = asyncio.create_task(_watch_loop(outbox, stop))
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
        stop.set()
        for task in (watcher, sender):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, ConnectionClosed):
                await task


async def _serve() -> int:
    """Dial groom and hold a session open, reconnecting with backoff (built into ``connect``) whenever the socket drops."""
    uri = f"ws://{GROOM_HOST}:{GROOM_PORT}/sidecar"
    async for ws in connect(uri):
        try:
            await _run_session(ws)
        except ReloadRequested:
            with contextlib.suppress(Exception):
                await ws.close()
            return RELOAD_EXIT_CODE
        except ConnectionClosed:
            continue
    return 0


def run() -> None:
    exit_code = asyncio.run(_serve())
    if exit_code:
        raise SystemExit(exit_code)
