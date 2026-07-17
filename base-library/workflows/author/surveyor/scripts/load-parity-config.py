#!/usr/bin/env python3
"""Resolve and validate the two documentation inventories for a parity survey."""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(os.environ.get("AGENT_REPO_DIR", Path.cwd())).resolve()


def main(logger: logging.Logger) -> None:
    baseline = sys.argv[1].strip() if len(sys.argv) > 1 else ""
    target = (sys.argv[2].strip() if len(sys.argv) > 2 else "") or "docs/features"
    survey_dir = (sys.argv[3].strip() if len(sys.argv) > 3 else "") or "docs/survey/legacy-vs-new"
    backlog = (sys.argv[4].strip() if len(sys.argv) > 4 else "") or "docs/backlog.md"
    epics = (sys.argv[5].strip() if len(sys.argv) > 5 else "") or "docs/epics"
    root = repo_root()
    if not baseline or not (root / baseline).is_file():
        logger.warning("baseline inventory not found: %s", baseline or "(empty)")
        raise SystemExit(f"[load-parity-config] baseline inventory not found: {baseline or '(empty)'}")
    if not (root / target).is_dir():
        logger.warning("target feature book not found: %s", target)
        raise SystemExit(f"[load-parity-config] target feature book not found: {target}")
    cfg = {
        "repo_root": str(root),
        "baseline_inventory": baseline,
        "target_features": target,
        "survey_dir": survey_dir,
        "inventory": f"{survey_dir}/inventory.json",
        "findings_dir": f"{survey_dir}/findings",
        "unit_manifest": f"{survey_dir}/unit-manifest.json",
        "backlog": backlog,
        "epics_dir": epics,
    }
    logger.info("config loaded: baseline=%s target=%s survey_dir=%s", baseline, target, survey_dir)
    print(json.dumps({"cfg": cfg}))


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("load-parity-config"))
