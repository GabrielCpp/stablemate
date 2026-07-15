#!/usr/bin/env python3
"""Operator gate for the plan stage (story-coder / coder).

A plan node concluded the work is genuinely BLOCKED on input only a human can
provide, or planning failed to converge within the rework budget. Instead of
looping or fabricating, we surface the questions in ``<story-folder>/context.md``
and BLOCK IN PLACE (this process does not exit): it watches context.md for a
change via inotify and wakes up as soon as the operator (or ``groom``, on the
operator's behalf) sets ``STATUS: ANSWERED``, then continues — no container
restart is involved. The container never stops on this path.

State machine, read from the first ``STATUS:`` line in context.md (matched as a
whole line, so prose that merely mentions the words is ignored):
  AWAITING_OPERATOR -> still waiting; block until the file changes, then re-check
  ANSWERED          -> operator answered; flip the line to CONSUMED, emit answers,
                       proceed (exit 0)
  CONSUMED          -> we already used an answer but the node blocked AGAIN, so the
                       answer didn't resolve it: append the new questions, re-arm the
                       line to AWAITING_OPERATOR, and block again — avoids an infinite
                       "answered" loop on a stale answer
  (missing/unknown) -> ensure an AWAITING line exists, then block

If inotify can't be set up at all (e.g. this ever runs on a non-Linux host), this
falls back to the old behavior of exiting 2 so the operator restarts the container
by hand — a safety net, not the expected path.

Args:
    argv[1]  story_path : repo-relative path to story.md (its dir holds context.md)
    argv[2]  questions   : the blocking node's questions/notes (optional)

Stdlib-only: scripts run under the system ``python3``, not the uv venv. This is why
the wait uses a small ``ctypes`` binding of the raw inotify syscalls instead of the
third-party ``inotify_simple`` package that groom's in-container sidecar uses — that
package isn't available under the system interpreter these scripts run under. On the
proceed path prints JSON (resets the rework budget so the reworked plan gets a
fresh loop allowance):
  {"operator_input": {"answered": true, "content": "<context.md>"},
   "plan_rework_count": {"value": 0}}
"""

import ctypes
import json
import os
import re
import select
import socket
import sys
import urllib.request
from pathlib import Path

AWAITING = "AWAITING_OPERATOR"
ANSWERED = "ANSWERED"
CONSUMED = "CONSUMED"

_STATUS_RE = re.compile(r"^STATUS:[ \t]*(\S+)", re.MULTILINE)
# Optional operator-chosen scope for the fix (epic runs only). `story` reworks just
# this story's plan; `epic` triggers a replan of the whole epic + its stories.
_SCOPE_RE = re.compile(r"^SCOPE:[ \t]*(\S+)", re.MULTILINE)

# Raw inotify syscalls via ctypes (see module docstring for why not
# inotify_simple). Mask/flag values are the fixed Linux x86_64 constants from
# <sys/inotify.h> — these containers only ever run on Linux/x86_64.
_IN_MODIFY = 0x00000002
_IN_CLOSE_WRITE = 0x00000008
_IN_CREATE = 0x00000100
_IN_MOVED_TO = 0x00000080
_WATCH_MASK = _IN_MODIFY | _IN_CLOSE_WRITE | _IN_CREATE | _IN_MOVED_TO
# Re-check even with no inotify event, so we still notice a change if some
# write pattern doesn't trip the watched flags.
_HEARTBEAT_SECONDS = 300.0
try:
    _libc = ctypes.CDLL("libc.so.6", use_errno=True)
except OSError:
    # Non-Linux host (e.g. a macOS dev sandbox) — no libc.so.6 to bind. Leave
    # _libc unset; _inotify_init() below raises OSError on first use, which
    # _block_for_change() already catches to fall back to exit(2) (see module
    # docstring), instead of crashing here at import time.
    _libc = None

story_path = sys.argv[1] if len(sys.argv) > 1 else ""
questions = (
    sys.argv[2].strip() if len(sys.argv) > 2 else ""
) or "No specific questions were recorded."


# Scripts run from the workflow dir, not the repo. Resolve the repo root (marked by
# agents.yml or .git) so the repo-relative story_path points at the real folder.
# The test harness sets CWD to the sandbox; production sets AGENT_REPO_DIR.
def _find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    cwd = Path.cwd()
    if (
        (cwd / "docs" / "epics").is_dir()
        or (cwd / "agents.yml").exists()
        or (cwd / ".git").exists()
    ):
        return cwd
    for candidate in cwd.parents:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    here = Path(__file__).resolve().parent
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return cwd


root = _find_repo_root()

ctx = (root / story_path).parent / "context.md" if story_path else root / "context.md"


def status_of(text: str) -> str:
    m = _STATUS_RE.search(text)
    return m.group(1).upper() if m else ""


def scope_of(text: str) -> str:
    """Operator-chosen fix scope: 'epic' (replan the epic + stories) or 'story'
    (default; rework just this plan). Unknown values fall back to 'story'."""
    m = _SCOPE_RE.search(text)
    val = m.group(1).lower() if m else "story"
    return "epic" if val == "epic" else "story"


def set_status(text: str, new: str) -> str:
    return _STATUS_RE.sub(f"STATUS: {new}", text, count=1)


def banner() -> None:
    print(
        "\n".join(
            [
                "============================================================",
                "⛔ BLOCKED — operator input required (expected, NOT a crash).",
                "The workflow paused and will resume when you answer.",
                f"    {ctx}",
                f"Set the 'STATUS: {AWAITING}' line to 'STATUS: {ANSWERED}', add your",
                "answers, then re-run the workflow to resume from this point.",
                "============================================================",
            ]
        ),
        file=sys.stderr,
    )


def fresh_body() -> str:
    return (
        "# Operator Context — action required\n\n"
        f"STATUS: {AWAITING}\n"
        "SCOPE: story   # epic runs only: set to `epic` to replan the whole epic +\n"
        "               # its stories (not just this story's plan)\n\n"
        "The autonomous workflow paused because it needs input only you can\n"
        "provide. Answer below, change the STATUS line above to\n"
        f"`STATUS: {ANSWERED}`, then re-run the workflow.\n\n"
        f"## Questions from the agent\n\n{questions}\n\n"
        "## Your answers\n\n<!-- write your answers here -->\n"
    )


def _push_blocked_backstop() -> None:
    """Best-effort direct push to a host-side ``groom`` dashboard, in case this
    halt's file-write races the in-container groom-sidecar's inotify callback
    before the container tears down. Silent no-op if groom isn't reachable —
    same discipline as groom/sidecar.py's own push() (short timeout, broad
    except, never affects this script's exit code). Stdlib-only: no new
    dependency in this shared script.
    """
    try:
        rel_path = str(ctx.relative_to("/workspace"))
    except ValueError:
        rel_path = str(ctx)
    body = json.dumps(
        {
            "container_id": socket.gethostname()[:12],
            "name": os.environ.get("REPO_NAME", socket.gethostname()),
            "repo_name": os.environ.get("REPO_NAME", ""),
            "repo_branch": os.environ.get("REPO_BRANCH", ""),
            "file_path": rel_path,
            "question": questions,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"http://{os.environ.get('GROOM_HOST', 'host.docker.internal')}:{os.environ.get('GROOM_PORT', '8787')}/push/blocked",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(request, timeout=1.0).close()
    except Exception:
        pass


def _inotify_init() -> int:
    if _libc is None:
        raise OSError("libc.so.6 unavailable (not a Linux host)")
    fd = _libc.inotify_init1(0)
    if fd < 0:
        errno_ = ctypes.get_errno()
        raise OSError(errno_, os.strerror(errno_))
    return fd


def _inotify_add_watch(fd: int, path: str, mask: int) -> None:
    wd = _libc.inotify_add_watch(fd, path.encode(), mask)
    if wd < 0:
        errno_ = ctypes.get_errno()
        raise OSError(errno_, os.strerror(errno_))


def _block_for_change() -> None:
    """Block until ctx's directory reports a write-relevant inotify event, or
    ``_HEARTBEAT_SECONDS`` elapses. Falls back to the legacy exit(2) if
    inotify can't be set up at all (see module docstring).
    """
    try:
        fd = _inotify_init()
        _inotify_add_watch(fd, str(ctx.parent), _WATCH_MASK)
    except OSError as exc:
        print(
            f"[await-operator] inotify unavailable ({exc}) — falling back to exit(2)",
            file=sys.stderr,
        )
        sys.exit(2)
    try:
        ready, _, _ = select.select([fd], [], [], _HEARTBEAT_SECONDS)
        if ready:
            os.read(fd, 4096)
    finally:
        os.close(fd)


_banner_shown = False


def halt() -> None:
    """Block in place (no exit) until ctx's STATUS line changes. The banner
    and backstop push only fire once per distinct block so re-checks after a
    heartbeat wakeup don't spam either.
    """
    global _banner_shown
    if not _banner_shown:
        banner()
        _push_blocked_backstop()
        _banner_shown = True
    _block_for_change()


while True:
    if not ctx.exists():
        ctx.parent.mkdir(parents=True, exist_ok=True)
        ctx.write_text(fresh_body())
        print(f"[await-operator] wrote {ctx}", file=sys.stderr)
        halt()
        continue

    current = ctx.read_text()
    state = status_of(current)

    if state == ANSWERED:
        # Consume the answer: flip to CONSUMED so a later re-block re-arms instead of
        # looping forever on the same stale answer.
        ctx.write_text(set_status(current, CONSUMED))
        print(
            json.dumps(
                {
                    "operator_input": {
                        "answered": True,
                        "scope": scope_of(current),
                        "content": current,
                    },
                    "plan_rework_count": {"value": 0},
                }
            )
        )
        sys.exit(0)

    if state == AWAITING:
        print(
            f"[await-operator] {ctx} still {AWAITING} — waiting for the operator (blocking, no restart needed)",
            file=sys.stderr,
        )
        halt()
        continue

    if state == CONSUMED:
        # We already used an answer but we're blocked AGAIN — it didn't resolve the
        # block. Re-arm and append the new questions so the operator sees the renewed ask.
        rearmed = set_status(current, AWAITING) + (
            "\n\n## Follow-up questions (still blocked after your last answer)\n\n"
            f"{questions}\n\n## Your answers (follow-up)\n\n<!-- write here -->\n"
        )
        ctx.write_text(rearmed)
        print(
            f"[await-operator] re-blocked after a consumed answer — re-armed {ctx}",
            file=sys.stderr,
        )
        _banner_shown = False  # new follow-up questions — notify again
        halt()
        continue

    # No recognizable STATUS line — ensure one exists so the operator has a marker to
    # flip, then wait without clobbering whatever they may have written.
    print(
        f"[await-operator] {ctx} has no STATUS line — adding one and waiting",
        file=sys.stderr,
    )
    ctx.write_text(f"STATUS: {AWAITING}\n\n" + current)
    halt()
    continue
