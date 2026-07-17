#!/usr/bin/env python3
"""Load surveyor-workflow config and validate the rubric exists → `cfg`.

Start node of the surveyor workflow. Resolves the repo root (the consuming repo, not
the shared library) and verifies the **rubric** document the run was pointed at
actually exists — failing fast with a clear message rather than letting the planner
and assessors hallucinate a concern from an empty file. The rubric is the surveyor's
ONLY project-facing input: it defines the cross-cutting concern being surveyed (what
counts as a finding, what "clean" means) and points at any repo skills the assessors
should read. The workflow itself stays concern- and stack-generic.

Everything else in `cfg` is a path convention under `survey_dir`:

  - rules          : enumeration rules (planner-authored, or operator-pinned — an
                     existing file beats the planner, same precedence as research's
                     program selection)
  - inventory      : the materialized unit list — durable, committed, FROZEN once built
  - findings_dir   : one finding record per unit (markdown + YAML front-matter)
  - partition      : the epic/story cluster file the partitioner writes
  - unit_manifest  : the emitted unit-level manifest the author workflow's
                     `coverage_mode: "full"` gate consumes (the role
                     `cfg.surface_manifest` plays in author)
  - context        : the shared operator context.md for blocked gates

Stdlib-only: scripts run under the system ``python3``, not the uv venv.

Args:
    argv[1]  rubric     : repo-relative path to the rubric markdown (REQUIRED)
    argv[2]  survey_dir : survey artifacts root (default docs/survey)
    argv[3]  backlog    : backlog file the survey emits into (default docs/backlog.md)

Outputs JSON: {"cfg": {repo_root, rubric, survey_dir, rules, inventory, findings_dir,
                       partition, backlog, unit_manifest, context}}
"""
from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path


def find_repo_root() -> Path:
    # AGENT_REPO_DIR is pinned to the consuming repo by the makefile; the script's own
    # location points into the shared library, so prefer the env var.
    env_root = os.environ.get("AGENT_REPO_DIR")
    if env_root:
        return Path(env_root).resolve()
    here = Path.cwd().resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "agents.yml").exists() or (candidate / "docs" / "epics").is_dir():
            return candidate
    return here


def main(logger: logging.Logger) -> None:
    rubric = (sys.argv[1].strip() if len(sys.argv) > 1 and sys.argv[1] else "") or "docs/survey/rubric.md"
    survey_dir = (sys.argv[2].strip() if len(sys.argv) > 2 and sys.argv[2] else "") or "docs/survey"
    backlog = (sys.argv[3].strip() if len(sys.argv) > 3 and sys.argv[3] else "") or "docs/backlog.md"

    root = find_repo_root()
    rubric_path = (root / rubric).resolve()
    if not rubric_path.is_file():
        logger.warning("rubric file not found: %s", rubric_path)
        sys.exit(
            f"[load-config] rubric file not found: {rubric_path}\n"
            f"Create {rubric} (a markdown document defining the cross-cutting concern being "
            f"surveyed: what counts as a finding, what 'clean' means, and which repo skills "
            f"the assessors should read) before running the surveyor workflow, or pass "
            f"--params '{{\"rubric\":\"<path>\"}}'."
        )

    cfg = {
        "repo_root": str(root),
        "rubric": rubric,
        "survey_dir": survey_dir,
        "rules": f"{survey_dir}/units.yml",
        "inventory": f"{survey_dir}/inventory.json",
        "findings_dir": f"{survey_dir}/findings",
        "partition": f"{survey_dir}/partition.yaml",
        "backlog": backlog,
        "unit_manifest": f"{survey_dir}/unit-manifest.json",
        "context": f"{survey_dir}/_survey-context.md",
    }
    logger.info("config loaded: rubric=%s survey_dir=%s repo_root=%s", rubric, survey_dir, root)
    print(json.dumps({"cfg": cfg}))


if __name__ == "__main__":
    # workhorse imports this and calls main(logger) itself; this guard is only for
    # running the script by hand.
    logging.basicConfig(level=logging.INFO, format="[%(name)s] %(message)s")
    main(logging.getLogger("load-config"))
