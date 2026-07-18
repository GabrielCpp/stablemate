#!/usr/bin/env python3
"""Convert an execution reviewer's product diagnosis into a QA failure."""

from __future__ import annotations

import json
import logging
import sys


def main(logger: logging.Logger) -> None:
    notes = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] else "QA assessment found a product defect."
    logger.info("QA execution assessment found a product defect: %s", notes)
    print(json.dumps({"qa_result": {"status": "failed", "notes": notes}}))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("mark-qa-assessment-failed"))
