"""One headless Chromium the machine's runs share, each in its own context, instead of a browser per run.

A run asks `connect(playwright)` for the shared browser. The first run on the machine
starts it as a detached server, and later runs connect to it over CDP. The server
closes after `IDLE_S` with no page open and no run connecting. A server that cannot
be reached answers None, and the caller launches its own browser as before.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from importlib import metadata
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError

SWITCH = "OSTLER_SHARED_BROWSER"

IDLE_S = 600.0

POLL_S = 15.0

START_S = 30.0

MEMORY_MAX = "6G"


def enabled() -> bool:
    return os.environ.get(SWITCH, "1") != "0"


def home() -> Path:
    cache = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return Path(cache) / "ostler" / "shared-browser" / metadata.version("playwright")


def connect(playwright: Any) -> Any | None:
    """The shared browser, connected over CDP, or None when sharing is off or the server cannot be reached."""
    if not enabled():
        return None
    try:
        root = home()
        root.mkdir(parents=True, exist_ok=True)
        with _locked(root):
            endpoint = _live(root) or _start(root)
            if endpoint is None:
                print(f"ostler: the shared browser did not start, see {root / 'server.log'}", file=sys.stderr)
                return None
            (root / "lease").touch()
            return playwright.chromium.connect_over_cdp(endpoint, timeout=START_S * 1000)
    except (OSError, subprocess.SubprocessError, PlaywrightError) as exc:
        print(f"ostler: launching an own browser, the shared one is out of reach: {exc}", file=sys.stderr)
        return None


@contextlib.contextmanager
def _locked(root: Path) -> Iterator[None]:
    with open(root / "lock", "a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _answers(endpoint: str, path: str = "/json/version") -> Any | None:
    try:
        with urllib.request.urlopen(endpoint + path, timeout=2) as response:  # noqa: S310 - a loopback endpoint this module wrote
            return json.load(response)
    except (OSError, ValueError):
        return None


def _live(root: Path) -> str | None:
    try:
        endpoint = json.loads((root / "endpoint").read_text())["endpoint"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return endpoint if _answers(endpoint) is not None else None


def _start(root: Path) -> str | None:
    (root / "endpoint").unlink(missing_ok=True)
    argv = [sys.executable, str(Path(__file__).resolve()), "serve", str(root)]
    with open(root / "server.log", "ab") as log:
        if not _start_unit(argv, log, root / "server.log"):
            subprocess.Popen(  # noqa: S603 - fixed argv
                argv, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
            )
    deadline = time.monotonic() + START_S
    while time.monotonic() < deadline:
        endpoint = _live(root)
        if endpoint is not None:
            return endpoint
        time.sleep(0.2)
    return None


def _start_unit(argv: list[str], log: Any, written: Path) -> bool:
    """Starts the server as its own user service, outside the cgroup of the run that asked, where systemd answers."""
    systemd_run = shutil.which("systemd-run")
    if systemd_run is None:
        return False
    passed = [f"--setenv={key}={value}" for key, value in os.environ.items()
              if key in ("PLAYWRIGHT_BROWSERS_PATH", "PATH", "HOME", "XDG_CACHE_HOME")]
    done = subprocess.run(  # noqa: S603 - fixed argv
        [systemd_run, "--user", "--quiet", "--collect", f"--unit=ostler-shared-browser-{os.getpid()}-{time.time_ns()}",
         "-p", f"MemoryMax={MEMORY_MAX}", "-p", "MemorySwapMax=0", "-p", "OOMPolicy=kill",
         "-p", f"StandardOutput=append:{written}", "-p", f"StandardError=append:{written}", *passed, "--", *argv],
        stdin=subprocess.DEVNULL, stdout=log, stderr=log, timeout=15, check=False,
    )
    return done.returncode == 0


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def _idle(root: Path, endpoint: str) -> bool:
    pages = _answers(endpoint, "/json/list")
    if pages is None:
        return True
    if any(target.get("type") == "page" for target in pages):
        return False
    try:
        leased = (root / "lease").stat().st_mtime
    except OSError:
        leased = 0.0
    return time.time() - leased > IDLE_S


def serve(root: Path) -> None:
    from playwright.sync_api import sync_playwright

    port = _free_port()
    endpoint = f"http://127.0.0.1:{port}"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=[f"--remote-debugging-port={port}"])
        written = root / "endpoint.tmp"
        written.write_text(json.dumps({"endpoint": endpoint, "pid": os.getpid()}))
        written.replace(root / "endpoint")
        (root / "lease").touch()
        while True:
            time.sleep(POLL_S)
            with _locked(root):
                if _idle(root, endpoint):
                    (root / "endpoint").unlink(missing_ok=True)
                    break
        if browser.is_connected():
            browser.close()

if __name__ == "__main__":
    serve(Path(sys.argv[2]))
