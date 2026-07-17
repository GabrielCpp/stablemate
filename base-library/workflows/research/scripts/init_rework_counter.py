#!/usr/bin/env python3
"""Reset the per-gate rework counter to zero.

Outputs JSON: {"rework_count": {"value": 0}}
"""
import json
import logging


def main(logger: logging.Logger) -> None:
    logger.info("resetting rework_count to 0")
    print(json.dumps({"rework_count": {"value": 0}}))


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("init_rework_counter"))
