#!/usr/bin/env python3
"""Remove stale QA evidence before context generation and planning.

Both pipeline and standalone QA use this node before context generation:

1. ``spec_dir`` must exist so context generation and planning can write inputs.
2. The disposable ``qa/`` output directory is removed in full.
3. The stale root ``qa-evidence.json`` verdict is removed as well.

The Ostler runner recreates ``qa/`` and owns its log, manifest, and evidence.
This script deliberately does not recreate or author any runner output.

Args: <spec_dir_abs>
Outputs JSON: {"qa_cleared": "yes"}
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path


def main(logger: logging.Logger) -> None:
    spec_dir = (
        Path(sys.argv[1]).resolve() if len(sys.argv) > 1 and sys.argv[1] else None
    )
    if spec_dir:
        spec_dir.mkdir(parents=True, exist_ok=True)
        qa_dir = spec_dir / "qa"
        if qa_dir.exists():
            shutil.rmtree(qa_dir)
            logger.info("removed stale qa dir %s", qa_dir)
        evidence_path = spec_dir / "qa-evidence.json"
        if evidence_path.exists():
            evidence_path.unlink()
            logger.info("removed stale evidence file %s", evidence_path)
    else:
        logger.warning("no spec_dir given — nothing to clear")

    print(json.dumps({"qa_cleared": "yes"}))


if __name__ == "__main__":
    # workhorse calls main(logger) itself; this guard is only for running by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("clear-qa-evidence"))
