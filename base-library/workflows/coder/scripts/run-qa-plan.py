#!/usr/bin/env python3
"""Invoke ``ostler qa run`` and normalize its expected four-state outcome.

Usage: run-qa-plan.py <spec_dir> [docs_path]
  docs_path: docs repo root; empty → AGENT_REPO_DIR / CWD (see find_docs_root). Script
    nodes run with cwd = the workflow definition's own directory, not the consuming
    repo, so without this the ``ostler`` graph root (and every relative path the QA
    plan's commands assume, e.g. ``cd infra``) resolves against the wrong repo.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from workhorse.scriptutil import find_docs_root, fresh_import

STATUSES = {"passed", "failed", "blocked", "invalid"}


def main(logger: logging.Logger) -> None:
    qa_cli = fresh_import("qa_cli", also_purge=("ostler",))
    spec_dir = sys.argv[1] if len(sys.argv) > 1 else ""
    docs_path_arg = sys.argv[2] if len(sys.argv) > 2 else ""
    plan = str(Path(spec_dir) / "qa-plan.yml")
    docs_root = find_docs_root(docs_path_arg)
    _returncode, payload, stderr = qa_cli.qa_run(plan, spec_dir, docs_root=docs_root)
    status = str(payload.get("status", "invalid")).lower()
    if status not in STATUSES:
        status = "invalid"
    notes = qa_cli.notes_for(payload, stderr, f"Ostler QA run returned {status}.")
    logger.info("ostler qa run for %s returned status=%s", spec_dir, status)
    qa_cli.emit("qa_result", status, notes, payload)


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("run-qa-plan"))
