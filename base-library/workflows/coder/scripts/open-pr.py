#!/usr/bin/env python3
"""Open the current epic's PR and tell the workflow to gate on its CI before merging.

Args: <epic> [<base_branch>=main]

Outputs JSON: {"should_gate": "yes|no", "ci_epic": "<epic>", "ci_base": "<base>"}
"""
from __future__ import annotations

import json
import logging
import runpy
import sys
from contextlib import redirect_stdout
from pathlib import Path

def _run_sibling(script: Path, argv: list[str]) -> None:
    """Run a helper script in-process so test monkeypatches remain visible."""
    old_argv = sys.argv[:]
    try:
        sys.argv = [str(script), *argv]
        with redirect_stdout(sys.stderr):
            runpy.run_path(str(script), run_name="__main__")
    finally:
        sys.argv = old_argv


def main(logger: logging.Logger) -> None:
    epic = sys.argv[1] if len(sys.argv) > 1 else ""
    base = sys.argv[2] if len(sys.argv) > 2 else "main"

    if not epic:
        logger.info("no epic — nothing to PR")
        print(json.dumps({"should_gate": "no", "ci_epic": "", "ci_base": base}))
        return

    scripts_dir = Path(__file__).resolve().parent
    _run_sibling(scripts_dir / "gh-open-pr.py", [epic, base])

    print(json.dumps({"should_gate": "yes", "ci_epic": epic, "ci_base": base}))


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    main(logging.getLogger("open-pr"))
