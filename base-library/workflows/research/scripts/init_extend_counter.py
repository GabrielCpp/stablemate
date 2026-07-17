#!/usr/bin/env python3
"""Initialize the program self-extension counter to zero.

When the gate ladder is fully PASS, the research lead reviews the program against
its North star and may EXTEND it with new gates (self-extension) rather than
terminate. This counter bounds how many extension rounds one run may take, so a
program that never converges to reached/impossible cannot grow forever — it is a
safety backstop, not the intended stop (the lead's reached/impossible verdict is).

Outputs JSON: {"extend_count": {"value": 0}}
"""
import json
import logging


def main(logger: logging.Logger) -> None:
    logger.info("initializing extend_count to 0")
    print(json.dumps({"extend_count": {"value": 0}}))


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("init_extend_counter"))
