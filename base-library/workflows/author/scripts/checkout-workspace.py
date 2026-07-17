#!/usr/bin/env python3
"""Clone/update the author workspace using the repo-configured GitHub token.

Farrier only forwards opaque environment variables from agents.yml. This author
hook owns the GitHub-specific step: resolve workflow.githubTokenEnv through
gh-token.py, expose it transiently to Workhorse's provider-neutral Git checkout,
and never persist or print the token.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

from workhorse.scriptutil import checkout_workspace


def main(logger: logging.Logger) -> None:
    token_script = Path(__file__).resolve().with_name("gh-token.py")
    result = subprocess.run(
        [sys.executable, str(token_script)],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    token = result.stdout.strip()
    if not token:
        logger.error("no GitHub token configured for private repository checkout")
        raise SystemExit(1)

    os.environ["WORKHORSE_GIT_TOKEN"] = token
    checkout_workspace()


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("checkout-workspace"))
