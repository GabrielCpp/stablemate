"""The walk's runtime: the app under test, and the browser that looks at it.

Ported from `base-library/workflows/okf-builder/scripts/{boot-app,boot-browser}.py`. Both
scripts were **dual-mode**: the same file booted or tore down depending on whether `argv[1]`
was the literal `--teardown`, because a YAML `script` node names a file and a second file
would have duplicated the module. A node is a function, so the sentinel is gone and each
script becomes two nodes — `boot_app`/`teardown_app`, `boot_browser`/`teardown_browser` —
with the boot half typed as a boot (`AppBoot`, `BrowserBoot`) and the teardown half as a
teardown (`TornDown`). Nothing else about either changes; the app half remains a thin
wrapper over `workhorse.stack`, which the coder QA flow shares.

The YAML's mandatory-teardown tail (every exit from the walk routed through `teardown_app`
→ `teardown_browser` → `wt_done`) survives as `walkthrough_web/flow.py`'s `_finish`, which
every terminal calls. Because the pgids are state parameters rather than run-global vars, a
*resumed* walk can still reap what an earlier process started.
"""
from __future__ import annotations

import logging
import os
import shutil
import signal
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

from workhorse import stack
from workhorse_workflows.okf_builder.shared import paths
from workhorse_workflows.okf_builder.shared import stubs
from workhorse_workflows.okf_builder.shared.blueprint import blueprint
from workhorse_workflows.okf_builder.shared.schemas import AppBoot, BrowserBoot, TornDown

BOOT_TIMEOUT_S = 30.0
POLL_INTERVAL_S = 0.5
TERM_GRACE_S = 5.0
BROWSER_CANDIDATES = ("chromium-browser", "chromium", "google-chrome", "google-chrome-stable")


@blueprint.node(stub=stubs.app_up)
def boot_app(
    logger: logging.Logger,
    launch_cmd: str = "",
    entry_url: str = "",
    health_path: str = "/",
    app_cwd: str = ".",
    repo_root: str = "",
    app_identity: str = "",
    boot_timeout: str = "",
) -> AppBoot:
    """Start the app under walk and wait for it to answer its health path.

    The durable start logic lives in `workhorse.stack` so this walk and the coder QA flow
    share one implementation — including the identity check that keeps an unrelated process
    already holding the port from being mistaken for this service.
    """
    return AppBoot.model_validate(stack.boot_app(
        launch_cmd, entry_url, health_path or "/", app_cwd or ".",
        repo_root or app_cwd or ".", app_identity,
        stack.boot_timeout(boot_timeout), logger=logger,
    ))


@blueprint.node
def teardown_app(logger: logging.Logger, app_pgid: str = "", stop_cmd: str = "",
                 app_cwd: str = "") -> TornDown:
    """Reap the app this run started (or run its documented `stop:` recipe)."""
    return TornDown.model_validate(
        stack.teardown_app(app_pgid, stop_cmd, app_cwd, logger=logger)
    )


def _cdp_ok(cdp_url: str) -> bool:
    try:
        with urllib.request.urlopen(cdp_url.rstrip("/") + "/json/version", timeout=3) as r:  # noqa: S310 (loopback)
            return 200 <= r.status < 400
    except Exception:
        return False


@blueprint.node(stub=stubs.browser_up)
def boot_browser(logger: logging.Logger, cdp_url: str = "", repo_root: str = ".") -> BrowserBoot:
    """Own the shared CDP browser's lifecycle.

    One headless Chromium serves BOTH sides of visual registration: the agent's playwright
    MCP connects to it (`--cdp-endpoint` in the walked repo's opencode.json) to drive the
    page, and `ostler vet --cdp-url` attaches to the same browser to scan the very DOM the
    agent is looking at. It is started here, outside any agent turn — the agent runner reaps
    per-turn grandchildren, so a browser the MCP launched itself would not survive between
    turns, and vet could never see the MCP's page.

    Boot is idempotent (mirrors `boot_app`): if something already answers the CDP endpoint
    (a leftover from a crashed run), it is adopted rather than double-bound, and
    `browser_pgid` is left empty so teardown won't kill a process this run didn't start.
    """
    if not cdp_url:
        logger.warning("no CDP url supplied — cannot boot the shared browser")
        return BrowserBoot()
    port = urllib.parse.urlparse(cdp_url).port or 9222

    # Idempotent reuse: something already answering CDP here → adopt it, own nothing.
    if _cdp_ok(cdp_url):
        logger.info("adopting the browser already answering CDP at %s; "
                    "teardown will not reap it", cdp_url)
        return BrowserBoot(browser_ok=True, cdp_url=cdp_url)

    binary = next((b for b in BROWSER_CANDIDATES if shutil.which(b)), "")
    if not binary:
        # Without a browser there is no visual registration at all, and the walk's
        # screenshots and `ostler vet` both go quietly missing.
        logger.warning("no chromium binary on PATH (tried %s) — cannot boot the browser",
                       ", ".join(BROWSER_CANDIDATES))
        return BrowserBoot(cdp_url=cdp_url)

    root = Path(repo_root or ".")
    paths.ensure_build_dir(root)  # before the profile lands, or `git add -A` eats it
    scratch = paths.walkthrough_scratch(root)
    scratch.mkdir(parents=True, exist_ok=True)
    log = open(scratch / "browser.log", "ab")  # noqa: SIM115 (child keeps it open)
    cmd = [
        binary, "--headless=new", f"--remote-debugging-port={port}",
        f"--user-data-dir={scratch / 'browser-profile'}",
        "--no-first-run", "--no-default-browser-check", "about:blank",
    ]
    try:
        proc = subprocess.Popen(
            cmd, cwd=repo_root or ".",
            stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    except (OSError, ValueError) as exc:
        logger.warning("browser %s could not be spawned: %s", binary, exc)
        return BrowserBoot(cdp_url=cdp_url)

    pgid = os.getpgid(proc.pid)
    deadline = time.monotonic() + BOOT_TIMEOUT_S
    while time.monotonic() < deadline:
        if proc.poll() is not None:  # died on startup
            logger.warning("browser exited with code %s during startup — see %s",
                           proc.returncode, scratch / "browser.log")
            return BrowserBoot(cdp_url=cdp_url)
        if _cdp_ok(cdp_url):
            logger.info("browser is answering CDP at %s (pid %d, pgid %d)",
                        cdp_url, proc.pid, pgid)
            return BrowserBoot(browser_ok=True, cdp_url=cdp_url,
                               browser_pid=str(proc.pid), browser_pgid=str(pgid))
        time.sleep(POLL_INTERVAL_S)

    # Timed out: reap what we started so nothing is orphaned, then fail soft.
    logger.warning("browser did not answer CDP at %s within %.0fs — killing pgid %d "
                   "and failing soft", cdp_url, BOOT_TIMEOUT_S, pgid)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    return BrowserBoot(cdp_url=cdp_url)


@blueprint.node
def teardown_browser(logger: logging.Logger, browser_pgid: str = "") -> TornDown:
    """Reap the shared browser, if this run is the one that started it."""
    try:
        pgid = int(browser_pgid)
    except (TypeError, ValueError):
        # No pgid: boot adopted a browser it didn't start, so there is nothing to reap.
        logger.info("teardown skipped — no browser_pgid to kill (nothing this run started)")
        return TornDown(torn_down="skipped")
    logger.info("tearing down browser process group %d", pgid)
    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return TornDown(torn_down="yes")  # already gone
    deadline = time.monotonic() + TERM_GRACE_S
    while time.monotonic() < deadline:
        try:
            os.killpg(pgid, 0)  # still alive?
        except (ProcessLookupError, PermissionError, OSError):
            return TornDown(torn_down="yes")
        time.sleep(POLL_INTERVAL_S)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    return TornDown(torn_down="yes")


__all__ = ["boot_app", "boot_browser", "teardown_app", "teardown_browser"]
