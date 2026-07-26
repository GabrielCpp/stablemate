#!/usr/bin/env python3
"""Invoke ``ostler qa context-validate`` and normalize pass/invalid routing.

Usage: validate-qa-okf-context.py <spec_dir> <build_status> [output_key] [docs_path]
  docs_path: docs repo root; empty → AGENT_REPO_DIR / CWD (see find_docs_root). Script
    nodes run with cwd = the workflow definition's own directory, not the consuming
    repo, so without this the ``ostler`` graph root resolves against the wrong repo.
"""

from __future__ import annotations

import logging
import sys

from workhorse.scriptutil import find_docs_root, fresh_import


def main(logger: logging.Logger) -> None:
    qa_cli = fresh_import("qa_cli", also_purge=("ostler",))
    spec_dir = sys.argv[1] if len(sys.argv) > 1 else ""
    build_status = sys.argv[2] if len(sys.argv) > 2 else "invalid"
    output_key = sys.argv[3] if len(sys.argv) > 3 else "qa_context_result"
    docs_path_arg = sys.argv[4] if len(sys.argv) > 4 else ""
    docs_root = find_docs_root(docs_path_arg)
    returncode, payload, stderr = qa_cli.qa_context_validate(spec_dir, docs_root=docs_root)
    cli_status = str(payload.get("status", "invalid")).lower()
    status = (
        "passed"
        if returncode == 0 and build_status == "passed" and cli_status == "passed"
        else "invalid"
    )
    notes = qa_cli.notes_for(
        payload,
        stderr,
        "QA OKF context is valid."
        if status == "passed"
        else "QA OKF context is invalid.",
    )
    logger.info("qa context-validate for %s returned status=%s", spec_dir, status)
    qa_cli.emit(output_key, status, notes, payload)


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("validate-qa-okf-context"))
