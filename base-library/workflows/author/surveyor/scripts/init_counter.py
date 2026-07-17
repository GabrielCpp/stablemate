#!/usr/bin/env python3
"""Initialize a named rework counter to zero.

Generic replacement for coder's three hardcoded init_*_counter.py scripts: the
counter key is passed as argv[1] so one script serves every bounded loop in the
surveyor workflow (plan_rework_count, record_fix_count, partition_rework_count,
verify_resolve_count).

Reset once when a loop is (re)entered and read by the matching `guard_*` branch to
stop an unbounded produce<->rework loop — when it never converges, the guard routes
to the on-demand operator gate instead of looping forever.

Stdlib-only: scripts run under the system `python3`, not the uv venv.

Args:
    argv[1]  key : the counter variable name (e.g. "record_fix_count")

Outputs JSON: {"<key>": {"value": 0}}
"""
import json
import logging
import sys


def main(logger: logging.Logger) -> None:
    key = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else "rework_count"
    logger.info("initializing counter '%s' to 0", key)
    print(json.dumps({key: {"value": 0}}))


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("init_counter"))
