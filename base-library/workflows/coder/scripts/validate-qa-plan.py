#!/usr/bin/env python3
"""Invoke ``ostler qa validate`` and always emit passed/invalid routing JSON."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from qa_cli import emit, notes_for, qa_validate


def main(logger: logging.Logger) -> None:
    spec_dir = sys.argv[1] if len(sys.argv) > 1 else ""
    plan = str(Path(spec_dir) / "qa-plan.yml")
    returncode, payload, stderr = qa_validate(plan, spec_dir)
    cli_status = str(payload.get("status", "invalid")).lower()
    status = "passed" if returncode == 0 and cli_status == "passed" else "invalid"
    notes = notes_for(
        payload,
        stderr,
        "QA plan is valid." if status == "passed" else "QA plan is invalid.",
    )
    logger.info("qa validate for %s returned status=%s", spec_dir, status)
    emit("qa_plan_validation", status, notes, payload)


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("validate-qa-plan"))
