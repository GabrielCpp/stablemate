#!/usr/bin/env python3
"""okf-builder walkthrough: own the app-under-test's lifecycle (thin CLI wrapper).

The durable start/stop logic lives in :mod:`workhorse.stack` so the okf-builder
walkthrough and the coder QA flow share one implementation. This script is only the
argv + JSON-to-stdout contract the workflow's ``script`` nodes call.

Boot mode  — args: [launch_cmd] [entry_url] [health_path] [app_cwd] [repo_root]
                   [app_identity] [boot_timeout]
Teardown   — args: --teardown [app_pgid] [stop_cmd] [app_cwd]
Outputs JSON: {"boot_ok","entry_url","app_pid","app_pgid","torn_down"}
"""
from __future__ import annotations

import json
import logging
import sys

from workhorse import stack


def emit(**kw: object) -> None:
    payload: dict[str, object] = {
        "boot_ok": "no", "entry_url": "", "app_pid": "", "app_pgid": "",
        "torn_down": "no",
    }
    payload.update(kw)
    print(json.dumps(payload))
    sys.exit(0)


def main(logger: logging.Logger) -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--teardown":
        emit(**stack.teardown_app(
            sys.argv[2] if len(sys.argv) > 2 else "",
            sys.argv[3] if len(sys.argv) > 3 else "",
            sys.argv[4] if len(sys.argv) > 4 else "",
            logger=logger,
        ))

    launch_cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    entry_url = sys.argv[2] if len(sys.argv) > 2 else ""
    health_path = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] else "/"
    app_cwd = sys.argv[4] if len(sys.argv) > 4 and sys.argv[4] else "."
    repo_root = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5] else app_cwd
    app_identity = sys.argv[6] if len(sys.argv) > 6 else ""
    timeout_s = stack.boot_timeout(sys.argv[7] if len(sys.argv) > 7 else "")

    emit(**stack.boot_app(
        launch_cmd, entry_url, health_path, app_cwd, repo_root, app_identity,
        timeout_s, logger=logger,
    ))


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("boot-app"))
