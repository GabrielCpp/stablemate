#!/usr/bin/env python3
"""Open the current epic's PR and tell the workflow to gate on its CI before merging.

Args: <epic> [<base_branch>=main]

Outputs JSON: {"should_gate": "yes|no", "ci_epic": "<epic>", "ci_base": "<base>"}
"""
from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(name)s %(levelname)s: %(message)s")
    epic = sys.argv[1] if len(sys.argv) > 1 else ""
    base = sys.argv[2] if len(sys.argv) > 2 else "main"

    if not epic:
        logger.info("no epic — nothing to PR")
        print(json.dumps({"should_gate": "no", "ci_epic": "", "ci_base": base}))
        return

    scripts_dir = Path(__file__).resolve().parent
    subprocess.run(
        [sys.executable, str(scripts_dir / "gh-open-pr.py"), epic, base],
        stdout=sys.stderr, stderr=sys.stderr, text=True, check=False,
    )

    print(json.dumps({"should_gate": "yes", "ci_epic": epic, "ci_base": base}))


if __name__ == "__main__":
    main()
