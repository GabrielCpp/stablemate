#!/usr/bin/env python3
"""On-demand operator gate for the author workflow — records Q&A and resumes.

A producer (epic split, write-epic, story-split, write-story, coverage review)
concluded it is genuinely BLOCKED on input only a human can provide, or a bounded
loop never converged. Instead of looping or fabricating, we surface the questions in
a context.md and BLOCK IN PLACE (this process does not exit): it watches context.md
for a change via inotify and wakes up as soon as the operator (or ``groom``, on the
operator's behalf) sets ``STATUS: ANSWERED``, then continues — no container restart
is involved. The container never stops on this path.

This is coder's ``await_operator.py`` generalized: the context file path is passed
explicitly (not derived from a story folder), so one script serves every blocked
point. Each await node loops back to its producer, which re-reads its context.md and
continues — so the recorded answer is consumed exactly once (ANSWERED→CONSUMED) and
re-arms (CONSUMED→AWAITING) if the producer blocks again.

State machine, read from the first whole-line ``STATUS:`` in context.md:
  AWAITING_OPERATOR -> still waiting; block until the file changes, then re-check
  ANSWERED          -> flip to CONSUMED, emit answers, proceed (exit 0)
  CONSUMED          -> blocked AGAIN after a consumed answer: append the new
                       questions, re-arm to AWAITING_OPERATOR, block again
  (missing/unknown) -> ensure an AWAITING line exists, then block

If inotify can't be set up at all (e.g. this ever runs on a non-Linux host), this
falls back to the old behavior of exiting 2 so the operator restarts the container
by hand — a safety net, not the expected path.

Stdlib-only: scripts run under the system ``python3``, not the uv venv. This is why
the wait uses a small ``ctypes`` binding of the raw inotify syscalls instead of the
third-party ``inotify_simple`` package that groom's in-container sidecar uses — that
package isn't available under the system interpreter these scripts run under.

Args:
    argv[1]  context_path : repo-relative path to the context.md to use
    argv[2]  questions     : the blocking node's questions/notes (optional)
    argv[3]  counter_key   : optional rework-counter var to RESET to 0 on proceed

On the proceed path prints JSON:
  {"operator_input": {"answered": true, "content": "<context.md>"}
   [, "<counter_key>": {"value": 0}]}
"""
from __future__ import annotations

import ctypes
import json
import logging
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
_libc = ctypes.CDLL("libc.so.6", use_errno=True)

# `questions`, `counter_key`, `ctx`, `_banner_shown` are set inside main() (via
# `global`) from argv/cwd; the helper functions below resolve them as module
# globals at CALL time (Python's normal free-variable lookup), so this stays
# correct despite the assignments living inside main() rather than at import
# time. Placeholder values here only satisfy references before main() runs.
questions: str = "No specific questions were recorded."
counter_key: str = ""
ctx: Path | None = None
_banner_shown = False


def find_repo_root() -> Path:
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    cwd = Path.cwd()
    if (cwd / "docs" / "epics").is_dir() or (cwd / "agents.yml").exists() or (cwd / ".git").exists():
        return cwd
    for candidate in cwd.parents:
        if (candidate / "agents.yml").exists() or (candidate / ".git").exists():
            return candidate
    return cwd


def status_of(text: str) -> str:
    m = _STATUS_RE.search(text)
    return m.group(1).upper() if m else ""


def set_status(text: str, new: str) -> str:
    return _STATUS_RE.sub(f"STATUS: {new}", text, count=1)


def banner() -> None:
    print(
        "\n".join([
            "============================================================",
            "⛔ BLOCKED — operator input required (expected, NOT a crash).",
            "The author workflow paused and will resume when you answer.",
            f"    {ctx}",
            f"Set the 'STATUS: {AWAITING}' line to 'STATUS: {ANSWERED}', add your",
            "answers, then re-run the workflow to resume from this point.",
            "============================================================",
        ]),
        file=sys.stderr,
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
    body = json.dumps({
        "container_id": socket.gethostname()[:12],
        "name": os.environ.get("REPO_NAME", socket.gethostname()),
        "repo_name": os.environ.get("REPO_NAME", ""),
        "repo_branch": os.environ.get("REPO_BRANCH", ""),
        "file_path": rel_path,
        "question": questions,
    }).encode("utf-8")
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


def fresh_body() -> str:
    return (
        "# Author Workflow — operator input required\n\n"
        f"STATUS: {AWAITING}\n\n"
        "The autonomous author workflow paused because it needs input only you can\n"
        "provide (a product decision, a missing source-of-truth, an account/credential,\n"
        "a scope call). Answer below, change the STATUS line above to\n"
        f"`STATUS: {ANSWERED}`, then re-run the workflow.\n\n"
        f"## Questions from the agent\n\n{questions}\n\n"
        "## Your answers\n\n<!-- write your answers here -->\n"
    )


def proceed(text: str) -> None:
    payload: dict = {"operator_input": {"answered": True, "content": text}}
    if counter_key:
        payload[counter_key] = {"value": 0}
    print(json.dumps(payload))
    sys.exit(0)


def _inotify_init() -> int:
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
        print(f"[await-operator] inotify unavailable ({exc}) — falling back to exit(2)", file=sys.stderr)
        sys.exit(2)
    try:
        ready, _, _ = select.select([fd], [], [], _HEARTBEAT_SECONDS)
        if ready:
            os.read(fd, 4096)
    finally:
        os.close(fd)


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


def main(logger: logging.Logger) -> None:
    global ctx, questions, counter_key, _banner_shown

    context_rel = sys.argv[1] if len(sys.argv) > 1 else ""
    questions = (sys.argv[2].strip() if len(sys.argv) > 2 else "") or "No specific questions were recorded."
    counter_key = sys.argv[3].strip() if len(sys.argv) > 3 and sys.argv[3] else ""

    root = find_repo_root()
    ctx = (root / context_rel) if context_rel else (root / "_author-context.md")
    _banner_shown = False

    logger.info("await-operator watching %s", ctx)

    while True:
        if not ctx.exists():
            ctx.parent.mkdir(parents=True, exist_ok=True)
            ctx.write_text(fresh_body())
            print(f"[await-operator] wrote {ctx}", file=sys.stderr)
            logger.info("wrote fresh context file %s", ctx)
            halt()
            continue

        current = ctx.read_text()
        state = status_of(current)

        if state == ANSWERED:
            ctx.write_text(set_status(current, CONSUMED))
            logger.info("operator answered — proceeding")
            proceed(current)

        if state == AWAITING:
            print(f"[await-operator] {ctx} still {AWAITING} — waiting for the operator (blocking, no restart needed)", file=sys.stderr)
            halt()
            continue

        if state == CONSUMED:
            rearmed = set_status(current, AWAITING) + (
                "\n\n## Follow-up questions (still blocked after your last answer)\n\n"
                f"{questions}\n\n## Your answers (follow-up)\n\n<!-- write here -->\n"
            )
            ctx.write_text(rearmed)
            print(f"[await-operator] re-blocked after a consumed answer — re-armed {ctx}", file=sys.stderr)
            logger.info("re-blocked after a consumed answer — re-armed %s", ctx)
            _banner_shown = False  # new follow-up questions — notify again
            halt()
            continue

        # No recognizable STATUS line — add one without clobbering operator prose, then wait.
        print(f"[await-operator] {ctx} has no STATUS line — adding one and waiting", file=sys.stderr)
        ctx.write_text(f"STATUS: {AWAITING}\n\n" + current)
        halt()
        continue


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("await-operator"))
