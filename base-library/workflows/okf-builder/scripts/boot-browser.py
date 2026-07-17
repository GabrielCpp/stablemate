#!/usr/bin/env python3
"""okf-builder walkthrough: own the shared CDP browser's lifecycle.

One headless Chromium serves BOTH sides of visual registration: the agent's playwright
MCP connects to it (``--cdp-endpoint`` in the walked repo's opencode.json) to drive the
page, and ``ostler vet --cdp-url`` attaches to the same browser to scan the very DOM the
agent is looking at. It is started here, outside any agent turn — the agent runner reaps
per-turn grandchildren, so a browser the MCP launched itself would not survive between
turns, and vet could never see the MCP's page.

Boot is idempotent (mirrors boot-app.py): if something already answers the CDP endpoint
(a leftover from a crashed run), it is adopted rather than double-bound, and
``browser_pgid`` is left empty so teardown won't kill a process this run didn't start.

Boot mode  — args: [cdp_url] [repo_root]
Teardown   — args: --teardown [browser_pgid]
Outputs JSON: {"browser_ok","cdp_url","browser_pid","browser_pgid","torn_down"}
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BOOT_TIMEOUT_S = 30.0
POLL_INTERVAL_S = 0.5
TERM_GRACE_S = 5.0
BROWSER_CANDIDATES = ("chromium-browser", "chromium", "google-chrome", "google-chrome-stable")


def emit(**kw: object) -> None:
    payload: dict[str, object] = {
        "browser_ok": "no", "cdp_url": "", "browser_pid": "", "browser_pgid": "",
        "torn_down": "no",
    }
    payload.update(kw)
    print(json.dumps(payload))
    sys.exit(0)


def _cdp_ok(cdp_url: str) -> bool:
    try:
        with urllib.request.urlopen(cdp_url.rstrip("/") + "/json/version", timeout=3) as r:  # noqa: S310 (loopback)
            return 200 <= r.status < 400
    except Exception:
        return False


def _teardown(pgid_arg: str, logger: logging.Logger) -> None:
    try:
        pgid = int(pgid_arg)
    except (TypeError, ValueError):
        # No pgid: boot adopted a browser it didn't start, so there is nothing to reap.
        logger.info("teardown skipped — no browser_pgid to kill (nothing this run started)")
        emit(torn_down="skipped")  # nothing we own
    logger.info("tearing down browser process group %d", pgid)
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

    cdp_url = sys.argv[1] if len(sys.argv) > 1 else ""
    repo_root = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else "."
    if not cdp_url:
        logger.warning("no CDP url supplied — cannot boot the shared browser")
        emit(browser_ok="no")
    port = urllib.parse.urlparse(cdp_url).port or 9222

    # Idempotent reuse: something already answering CDP here → adopt it, own nothing.
    if _cdp_ok(cdp_url):
        logger.info("adopting the browser already answering CDP at %s; "
                    "teardown will not reap it", cdp_url)
        emit(browser_ok="yes", cdp_url=cdp_url, browser_pid="", browser_pgid="")

    binary = next((b for b in BROWSER_CANDIDATES if shutil.which(b)), "")
    if not binary:
        # Without a browser there is no visual registration at all, and the walk's
        # screenshots and `ostler vet` both go quietly missing.
        logger.warning("no chromium binary on PATH (tried %s) — cannot boot the browser",
                       ", ".join(BROWSER_CANDIDATES))
        emit(browser_ok="no", cdp_url=cdp_url)

    scratch = Path(repo_root) / ".agents" / "okf-build" / "walkthrough"
    scratch.mkdir(parents=True, exist_ok=True)
    log = open(scratch / "browser.log", "ab")  # noqa: SIM115 (child keeps it open)
    cmd = [
        binary, "--headless=new", f"--remote-debugging-port={port}",
        f"--user-data-dir={scratch / 'browser-profile'}",
        "--no-first-run", "--no-default-browser-check", "about:blank",
    ]
    try:
        proc = subprocess.Popen(
            cmd, cwd=repo_root,
            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        logger.warning("browser %s could not be spawned: %s", binary, exc)
        emit(browser_ok="no", cdp_url=cdp_url)

    pgid = os.getpgid(proc.pid)
    deadline = time.monotonic() + BOOT_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:  # died on startup
            logger.warning("browser exited with code %s during startup — see %s",
                           proc.returncode, scratch / "browser.log")
            emit(browser_ok="no", cdp_url=cdp_url)
        if _cdp_ok(cdp_url):
            logger.info("browser is answering CDP at %s (pid %d, pgid %d)",
                        cdp_url, proc.pid, pgid)
            emit(browser_ok="yes", cdp_url=cdp_url,
                 browser_pid=str(proc.pid), browser_pgid=str(pgid))
        time.sleep(POLL_INTERVAL_S)

    # Timed out: reap what we started so nothing is orphaned, then fail soft.
    logger.warning("browser did not answer CDP at %s within %.0fs — killing pgid %d "
                   "and failing soft", cdp_url, BOOT_TIMEOUT_S, pgid)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    emit(browser_ok="no", cdp_url=cdp_url)


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("boot-browser"))
