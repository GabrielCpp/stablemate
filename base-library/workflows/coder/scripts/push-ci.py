#!/usr/bin/env python3
"""CI-loop push step: re-push the epic branch and map the result to a status.

Args: <epic>

Outputs JSON: {"push_status": "pushed|unavailable|failed"}
"""
from __future__ import annotations

import json
import logging
import runpy
import sys
from contextlib import redirect_stdout
from pathlib import Path

UNAVAILABLE = 10


def _run_push_epic(script: Path, epic: str) -> int:
    old_argv = sys.argv[:]
    try:
        sys.argv = [str(script), epic]
        with redirect_stdout(sys.stderr):
            try:
                runpy.run_path(str(script), run_name="__main__")
            except SystemExit as exc:
                code = exc.code
                return 0 if code is None else (code if isinstance(code, int) else 1)
        return 0
    finally:
        sys.argv = old_argv


def main(logger: logging.Logger) -> None:
    epic = sys.argv[1] if len(sys.argv) > 1 else ""
    scripts_dir = Path(__file__).resolve().parent

    rc = _run_push_epic(scripts_dir / "push-epic.py", epic)

    if rc == 0:
        status = "pushed"
    elif rc == UNAVAILABLE:
        status = "unavailable"
    else:
        status = "failed"
    logger.info("push-epic for '%s' returned rc=%s — status=%s", epic, rc, status)

    print(json.dumps({"push_status": status}))


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    main(logging.getLogger("push-ci"))
