#!/usr/bin/env python3
"""Stamp a failed qa_result after the regression-fix budget is exhausted.

Args:
    argv[1]  regression_run.notes — the deterministic runner's summary of what's
             still failing (empty/absent → generic fallback text)
    argv[2]  regression_fix_count.value — attempts spent (empty/absent → "3")

Stdlib-only: scripts run under the system `python3`, not the uv venv.

Outputs JSON: {"qa_result": {"status": "failed", "notes": "..."}}
"""
import json
import sys

run_notes = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else "no failure detail captured"
attempts = sys.argv[2] if len(sys.argv) > 2 and sys.argv[2] else "3"

notes = (
    f"Regression suite still failing after {attempts} fix attempt(s): {run_notes}"
)
print(json.dumps({"qa_result": {"status": "failed", "notes": notes}}))
