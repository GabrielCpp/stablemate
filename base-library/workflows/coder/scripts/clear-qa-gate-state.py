#!/usr/bin/env python3
"""Clear consumed QA gate diagnostics before the next semantic review/run."""

from __future__ import annotations

import json
import logging


def main(logger: logging.Logger) -> None:
    logger.info("clearing consumed QA gate diagnostics")
    print(
        json.dumps(
            {
                "qa_plan_validation": {"notes": ""},
                "qa_plan_review": {"notes": ""},
                "qa_assessment": {"notes": ""},
                "qa_audit": {"notes": ""},
                "qa_result": {"notes": ""},
            }
        )
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("clear-qa-gate-state"))
