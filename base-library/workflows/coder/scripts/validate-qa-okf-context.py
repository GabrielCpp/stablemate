#!/usr/bin/env python3
"""Invoke ``ostler qa context-validate`` and normalize pass/invalid routing."""

from __future__ import annotations

import sys

from qa_cli import emit, notes_for, qa_context_validate


def main() -> None:
    spec_dir = sys.argv[1] if len(sys.argv) > 1 else ""
    build_status = sys.argv[2] if len(sys.argv) > 2 else "invalid"
    returncode, payload, stderr = qa_context_validate(spec_dir)
    cli_status = str(payload.get("status", "invalid")).lower()
    status = (
        "passed"
        if returncode == 0 and build_status == "passed" and cli_status == "passed"
        else "invalid"
    )
    notes = notes_for(
        payload,
        stderr,
        "QA OKF context is valid."
        if status == "passed"
        else "QA OKF context is invalid.",
    )
    emit("qa_context_result", status, notes, payload)


if __name__ == "__main__":
    main()
