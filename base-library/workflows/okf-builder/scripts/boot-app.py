#!/usr/bin/env python3
"""okf-builder walkthrough: own the app-under-test's lifecycle.

The agent runner (``runner/agent.py``) reaps per-turn grandchildren (the browser +
MCP), but it does NOT own the app being walked — that process is started here,
outside any agent turn, so the workflow must start AND stop it. Both are done via a
dedicated process group (``start_new_session=True`` + ``os.killpg``) so teardown
reaps uvicorn and any workers it forked.

Boot is idempotent: if the documented app identity is already serving the entry URL
(a leftover from a crashed run), it is reused rather than double-bound, and ``app_pgid``
is left empty so teardown won't kill a process this run didn't start. A different app
on the same port is never adopted.

Two shapes of launch command are supported, told apart by what the process does rather
than by a mode flag:

  * a FOREGROUND server (``npm run dev``, uvicorn) stays alive; exiting during startup
    means it died, and teardown reaps its process group.
  * a BRING-UP command (``make dev-stack-test-db``, ``docker compose up -d``) exits 0
    once the stack it started is serving *elsewhere* — in containers this process does
    not own. A clean exit is therefore not death: keep polling health to the deadline.
    Nothing is in our process group to reap, so teardown runs the documented ``stop:``
    recipe if the book has one, and otherwise leaves the stack up on purpose.

Boot mode  — args: [launch_cmd] [entry_url] [health_path] [app_cwd] [repo_root]
                   [app_identity] [boot_timeout]
Teardown   — args: --teardown [app_pgid] [stop_cmd] [app_cwd]
Outputs JSON: {"boot_ok","entry_url","app_pid","app_pgid","torn_down"}
"""
from __future__ import annotations

import json
import logging
import os
import shlex
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BOOT_TIMEOUT_S = 30.0     # a foreground dev server; overridable via `boot-timeout:`
POLL_INTERVAL_S = 0.5
TERM_GRACE_S = 5.0
STOP_TIMEOUT_S = 300.0    # ceiling on a documented `stop:` recipe


def _boot_timeout(raw: str) -> float:
    """The documented `boot-timeout:` in seconds, else the foreground-server default.

    A bring-up command that builds images is minutes, not seconds; a book that says so
    gets its ceiling. Junk falls back rather than crashing the walk.
    """
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return BOOT_TIMEOUT_S
    return value if value > 0 else BOOT_TIMEOUT_S


def emit(**kw: object) -> None:
    payload: dict[str, object] = {
        "boot_ok": "no", "entry_url": "", "app_pid": "", "app_pgid": "",
        "torn_down": "no",
    }
    payload.update(kw)
    print(json.dumps(payload))
    sys.exit(0)


def _health_ok(url: str, identity: str = "") -> bool:
    try:
        with urllib.request.urlopen(url, timeout=3) as r:  # noqa: S310 (loopback)
            if not 200 <= r.status < 400:
                return False
            if not identity:
                return True
            body = r.read(1_000_000).decode("utf-8", errors="replace")
            return identity in body
    except Exception:
        return False


def _teardown(pgid_arg: str, stop_cmd: str, app_cwd: str, logger: logging.Logger) -> None:
    try:
        pgid = int(pgid_arg)
    except (TypeError, ValueError):
        # No pgid: either boot adopted a process it didn't start, or the launch was a
        # bring-up command whose stack lives outside our process group. A documented
        # `stop:` recipe is the only way to reap the latter.
        if stop_cmd:
            logger.info("no app_pgid — running the documented stop recipe: %s", stop_cmd)
            try:
                done = subprocess.run(  # noqa: S603 (documented recipe, loopback stack)
                    shlex.split(stop_cmd), cwd=app_cwd or ".",
                    capture_output=True, text=True, timeout=STOP_TIMEOUT_S,
                )
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                logger.warning("stop recipe %r failed: %s — the app may still be running",
                               stop_cmd, exc)
                emit(torn_down="no")
            if done.returncode != 0:
                logger.warning("stop recipe exited %d — the app may still be running: %s",
                               done.returncode, (done.stderr or "").strip()[:500])
                emit(torn_down="no")
            emit(torn_down="yes")
        # No pgid and no stop recipe: leaving it up is the documented intent, not a leak.
        logger.info("teardown skipped — no app_pgid and no stop recipe "
                    "(nothing this run owns; an adopted or self-standing app is left up)")
        emit(torn_down="skipped")
    logger.info("tearing down app process group %d", pgid)
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        emit(torn_down="yes")  # already gone
    deadline = time.monotonic() + TERM_GRACE_S
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)  # still alive?
        except (ProcessLookupError, PermissionError, OSError):
            emit(torn_down="yes")
        time.sleep(POLL_INTERVAL_S)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    emit(torn_down="yes")


def main(logger: logging.Logger) -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--teardown":
        _teardown(
            sys.argv[2] if len(sys.argv) > 2 else "",
            sys.argv[3] if len(sys.argv) > 3 else "",
            sys.argv[4] if len(sys.argv) > 4 else "",
            logger,
        )

    launch_cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    entry_url = sys.argv[2] if len(sys.argv) > 2 else ""
    health_path = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else "/"
    app_cwd = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else "."
    repo_root = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] else app_cwd
    app_identity = sys.argv[6] if len(sys.argv) > 6 else ""
    timeout_s = _boot_timeout(sys.argv[7] if len(sys.argv) > 7 else "")
    health_url = entry_url.rstrip("/") + "/" + health_path.lstrip("/")

    if not launch_cmd:
        # The book documented no `launch:` recipe, so there is no app to boot. Reads as a
        # silent no-op downstream: the walk simply finds nothing serving.
        logger.warning("no launch command supplied — cannot boot the app under test")
        emit(boot_ok="no", entry_url=entry_url)

    # Idempotent reuse: something already serving here → adopt it, own nothing.
    # Reuse is safe only when the book provides an identity marker. Without one, start the
    # documented command and prove that owned process became healthy instead of adopting an
    # arbitrary listener on the same port.
    if app_identity and _health_ok(health_url, app_identity):
        logger.info("adopting the app already serving %s (identity %r matched); "
                    "teardown will not reap it", health_url, app_identity)
        emit(boot_ok="yes", entry_url=entry_url, app_pid="", app_pgid="")

    logger.info("booting app: %s (cwd %s), waiting up to %.0fs for %s",
                launch_cmd, app_cwd, timeout_s, health_url)

    log_dir = Path(repo_root) / ".agents" / "okf-build" / "walkthrough"
    log_dir.mkdir(parents=True, exist_ok=True)
    log = open(log_dir / "app.log", "ab")  # noqa: SIM115 (child keeps it open)
    try:
        proc = subprocess.Popen(
            shlex.split(launch_cmd), cwd=app_cwd,
            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        logger.warning("launch command %r could not be spawned: %s", launch_cmd, exc)
        emit(boot_ok="no", entry_url=entry_url)

    pgid = os.getpgid(proc.pid)
    detached = False  # the command returned; whatever it started serves outside our pgid
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        # Health first: a bring-up command can exit the instant the stack is serving, so
        # checking liveness first would race a successful boot into a spurious failure.
        if _health_ok(health_url, app_identity):
            if detached:
                # We own nothing to reap — report no pgid so teardown uses `stop:` (or
                # deliberately leaves the stack up) instead of killing an empty group.
                logger.info("app is healthy at %s (brought up by a command that has "
                            "since exited — this run owns no process to reap)", health_url)
                emit(boot_ok="yes", entry_url=entry_url, app_pid="", app_pgid="")
            logger.info("app is healthy at %s (pid %d, pgid %d)", health_url, proc.pid, pgid)
            emit(boot_ok="yes", entry_url=entry_url,
                 app_pid=str(proc.pid), app_pgid=str(pgid))
        if not detached and proc.poll() is not None:
            if proc.returncode != 0:
                logger.warning("app exited with code %s during startup — see %s",
                               proc.returncode, log_dir / "app.log")
                emit(boot_ok="no", entry_url=entry_url)
            # Exit 0 with nothing serving yet: a bring-up command that has handed the app
            # off to something it doesn't own (containers, a supervisor). Not death —
            # keep polling health to the deadline.
            logger.info("launch command exited cleanly without serving yet — treating it "
                        "as a bring-up command and waiting for %s", health_url)
            detached = True
        time.sleep(POLL_INTERVAL_S)

    if detached:
        # Nothing of ours to kill; the bring-up command may have left a partial stack, so
        # say so rather than implying a clean state.
        logger.warning("app did not answer %s within %.0fs after the bring-up command "
                       "exited — failing soft; anything it started is still up",
                       health_url, timeout_s)
        emit(boot_ok="no", entry_url=entry_url)

    # Timed out: reap what we started so nothing is orphaned, then fail soft.
    logger.warning("app did not answer %s within %.0fs — killing pgid %d and failing soft",
                   health_url, timeout_s, pgid)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    emit(boot_ok="no", entry_url=entry_url)


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("boot-app"))
