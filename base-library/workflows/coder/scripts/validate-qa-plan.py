#!/usr/bin/env python3
"""Invoke ``ostler qa validate`` and always emit passed/invalid routing JSON.

Usage: validate-qa-plan.py <spec_dir> [docs_path]
  docs_path: docs repo root; empty → AGENT_REPO_DIR / CWD (see find_docs_root). Script
    nodes run with cwd = the workflow definition's own directory, not the consuming
    repo, so without this the ``ostler`` graph root resolves against the wrong repo.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from workhorse.scriptutil import find_docs_root, fresh_import


def main(logger: logging.Logger) -> None:
    qa_cli = fresh_import("qa_cli", also_purge=("ostler",))
    spec_dir = sys.argv[1] if len(sys.argv) > 1 else ""
    docs_path_arg = sys.argv[2] if len(sys.argv) > 2 else ""
    plan = str(Path(spec_dir) / "qa-plan.yml")
    docs_root = find_docs_root(docs_path_arg)
    returncode, payload, stderr = qa_cli.qa_validate(plan, spec_dir, docs_root=docs_root)
    cli_status = str(payload.get("status", "invalid")).lower()
    status = "passed" if returncode == 0 and cli_status == "passed" else "invalid"
    notes = qa_cli.notes_for(
        payload,
        stderr,
        "QA plan is valid." if status == "passed" else "QA plan is invalid.",
    )
    logger.info("qa validate for %s returned status=%s", spec_dir, status)
    qa_cli.emit("qa_plan_validation", status, notes, payload)


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("validate-qa-plan"))
