#!/usr/bin/env python3
"""Initialize a named rework counter to zero.

Generic replacement for coder's three hardcoded init_*_counter.py scripts: the
counter key is passed as argv[1] so one script serves every bounded loop in the
author workflow (epics_rework_count, story_rework_count, cov_rework_count).

Reset once when a loop is (re)entered and read by the matching `guard_*` branch to
stop an unbounded produce<->rework loop — when it never converges, the guard routes
to the on-demand operator gate instead of looping forever.

Stdlib-only: scripts run under the system `python3`, not the uv venv.

Args:
    argv[1]  key : the counter variable name (e.g. "story_rework_count")

Outputs JSON: {"<key>": {"value": 0}}
"""
import json
import sys

key = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else "rework_count"
print(json.dumps({key: {"value": 0}}))
