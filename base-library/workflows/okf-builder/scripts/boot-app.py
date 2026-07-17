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

Boot mode  — args: [launch_cmd] [entry_url] [health_path] [app_cwd] [repo_root] [app_identity]
Teardown   — args: --teardown [app_pgid]
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

BOOT_TIMEOUT_S = 30.0
POLL_INTERVAL_S = 0.5
TERM_GRACE_S = 5.0


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


def _teardown(pgid_arg: str, logger: logging.Logger) -> None:
    try:
        pgid = int(pgid_arg)
    except (TypeError, ValueError):
        # No pgid: boot adopted a process it didn't start, so there is nothing to reap.
        logger.info("teardown skipped — no app_pgid to kill (nothing this run started)")
        emit(torn_down="skipped")  # nothing we own
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
        _teardown(sys.argv[2] if len(sys.argv) > 2 else "", logger)

    launch_cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    entry_url = sys.argv[2] if len(sys.argv) > 2 else ""
    health_path = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else "/"
    app_cwd = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else "."
    repo_root = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] else app_cwd
    app_identity = sys.argv[6] if len(sys.argv) > 6 else ""
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
                launch_cmd, app_cwd, BOOT_TIMEOUT_S, health_url)

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
    deadline = time.monotonic() + BOOT_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:  # died on startup
            logger.warning("app exited with code %s during startup — see %s",
                           proc.returncode, log_dir / "app.log")
            emit(boot_ok="no", entry_url=entry_url)
        if _health_ok(health_url, app_identity):
            logger.info("app is healthy at %s (pid %d, pgid %d)", health_url, proc.pid, pgid)
            emit(boot_ok="yes", entry_url=entry_url,
                 app_pid=str(proc.pid), app_pgid=str(pgid))
        time.sleep(POLL_INTERVAL_S)

    # Timed out: reap what we started so nothing is orphaned, then fail soft.
    logger.warning("app did not answer %s within %.0fs — killing pgid %d and failing soft",
                   health_url, BOOT_TIMEOUT_S, pgid)
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
