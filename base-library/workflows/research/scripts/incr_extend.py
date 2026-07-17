#!/usr/bin/env python3
"""Increment the program self-extension counter.

Args:
    argv[1]  current counter value

Outputs JSON: {"extend_count": {"value": <current + 1>}}
"""
import json
import logging
import sys


def main(logger: logging.Logger) -> None:
    current = int(float(sys.argv[1])) if len(sys.argv) > 1 and sys.argv[1] else 0
    logger.info("extend_count: %d -> %d", current, current + 1)
    print(json.dumps({"extend_count": {"value": current + 1}}))


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("incr_extend"))
