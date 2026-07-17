#!/usr/bin/env python3
"""Invoke ``ostler qa run`` and normalize its expected four-state outcome."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from qa_cli import emit, notes_for, qa_run

STATUSES = {"passed", "failed", "blocked", "invalid"}


def main(logger: logging.Logger) -> None:
    spec_dir = sys.argv[1] if len(sys.argv) > 1 else ""
    plan = str(Path(spec_dir) / "qa-plan.yml")
    _returncode, payload, stderr = qa_run(plan, spec_dir)
    status = str(payload.get("status", "invalid")).lower()
    if status not in STATUSES:
        status = "invalid"
    notes = notes_for(payload, stderr, f"Ostler QA run returned {status}.")
    logger.info("ostler qa run for %s returned status=%s", spec_dir, status)
    emit("qa_result", status, notes, payload)


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("run-qa-plan"))
