#!/usr/bin/env python3
"""Increment a named rework counter.

Generic replacement for coder's three hardcoded incr_*_rework.py scripts.

Args:
    argv[1]  key      : the counter variable name (e.g. "record_fix_count")
    argv[2]  current  : current counter value (empty/absent → treated as 0)

Read by the matching `guard_*` branch to cap a produce<->rework loop and escalate
to the operator gate once the rework budget is spent.

Stdlib-only: scripts run under the system `python3`, not the uv venv.

Outputs JSON: {"<key>": {"value": <current + 1>}}
"""
import json
import sys

key = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else "rework_count"
current = int(float(sys.argv[2])) if len(sys.argv) > 2 and sys.argv[2] else 0
print(json.dumps({key: {"value": current + 1}}))
