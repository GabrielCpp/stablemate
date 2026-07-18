#!/usr/bin/env python3
"""Convert an independent product refutation into the normal QA failure contract."""

from __future__ import annotations

import json
import logging
import sys


def main(logger: logging.Logger) -> None:
    notes = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else "QA audit found a product contradiction."
    logger.info("independent QA audit refuted the candidate pass: %s", notes)
    print(json.dumps({"qa_result": {"status": "failed", "notes": notes}}))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("mark-qa-audit-failed"))
